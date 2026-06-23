"""LLM narrative generation for the daily report's Korean prose sections.

The deterministic template renders every *figure* (counts, distances, dates).
This module asks an external, OpenAI-COMPATIBLE LLM to write only the
*qualitative* prose around those figures (개요 / 분석내용 / 향후추진 …).

Two hard invariants protect the boundary:

1. **Anonymized input.** The LLM is shown only the sanitized :class:`LLMFacts`
   (see :mod:`orbital_engine.reports.sanitize`), where every real identity is an
   opaque token ("OBJ-1", "OWN-2"). It never sees catalog ids/names/owners.

2. **No-numerals guard (CRITICAL).** Numbers are the template's job, and a
   hallucinated figure in the prose would be a data-integrity defect. After
   generation we validate the RAW (still-tokenized) prose: we strip the tokens
   that legitimately contain digits (OBJ-1 …) and then reject the output if ANY
   bare digit ``[0-9]`` survives. Only after the guard passes do we de-anonymize
   the tokens back to their originals via ``alias_map`` (originals may contain
   digits — fine, the guard already ran on the token form).

Retries: transient provider errors (rate-limit / timeout / connection) are
retried with exponential backoff up to ``settings.report_llm_max_retries``; a
guard rejection is retried ONCE with a stricter instruction. Exhaustion raises
:class:`SectionError`. The api key is never logged.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import openai

from orbital_engine.config import Settings, get_settings
from orbital_engine.reports.sanitize import LLMFacts, SanitizeResult

# Provider errors worth retrying: explicit rate-limit, plus the transient API
# errors (timeout / connection). RateLimitError subclasses APIStatusError;
# APITimeoutError / APIConnectionError subclass APIError. We catch the narrow
# transient set, NOT every APIError (a 400 bad-request must not be retried).
_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)

# A "digit not inside an allowed token" — used by the no-numerals guard after the
# allowed tokens have been removed from the text.
_DIGIT_RE = re.compile(r"[0-9]")

# The report's prose sections. Each maps to a (system, user-preamble) Korean
# prompt; the sanitized facts are appended to the user message as JSON.
SECTIONS: tuple[str, ...] = ("개요", "분석내용", "향후추진")


class SectionError(RuntimeError):
    """A prose section could not be generated within the configured budget.

    Raised on retry exhaustion, timeout, or a persistent no-numerals violation.
    """


def build_client(settings: Settings) -> openai.OpenAI:
    """Construct an OpenAI-compatible client from settings.

    ``max_retries=0`` so retry/backoff is owned by :func:`write_section` (the
    SDK's own retry layer would otherwise hide attempts from our budget and our
    tests). The free provider is selected purely by ``base_url``.
    """
    return openai.OpenAI(
        api_key=settings.report_llm_api_key,
        base_url=settings.report_llm_base_url,
        timeout=settings.report_llm_timeout_s,
        max_retries=0,
    )


def _system_prompt(section: str) -> str:
    return (
        "당신은 한국 우주영역인식(SDA) 일일 보고서의 문장을 작성하는 전문 분석관입니다. "
        f"지금 '{section}' 절의 서술형 문장만 작성합니다.\n"
        "반드시 다음 규칙을 지키십시오:\n"
        "1. 정성적(서술형) 한국어 문장만 작성합니다. 군더더기 없는 공식 보고서 문체를 사용합니다.\n"
        "2. 객체는 오직 토큰으로만 지칭합니다 (예: OBJ-1, OWN-2). 실제 명칭/식별번호를 추측하지 마십시오.\n"
        "3. 어떤 숫자(아라비아 숫자)도 쓰지 마십시오. 건수·거리·확률·날짜·시각 등 모든 수치는 "
        "보고서의 다른 곳(표/그래프)에서 자동으로 채워지므로 문장에 숫자를 넣으면 안 됩니다. "
        "'여러', '일부', '다수', '소수' 같은 정성적 표현만 사용하십시오.\n"
        "4. 토큰(OBJ-1 등) 안의 숫자는 식별자의 일부이므로 그대로 사용해도 됩니다."
    )


def _user_prompt(section: str, facts: LLMFacts, *, strict: bool = False) -> str:
    facts_json = facts.model_dump_json()
    body = (
        f"다음은 오늘 보고서의 익명화된 사실 데이터(JSON)입니다. 이를 근거로 '{section}' 절의 "
        "서술형 문장을 한국어로 작성하십시오. 객체는 토큰으로만 지칭하고, 문장에는 어떤 숫자도 "
        f"포함하지 마십시오.\n\n사실 데이터:\n{facts_json}"
    )
    if strict:
        body += (
            "\n\n[재작성 지시] 직전 출력에 숫자가 포함되어 거부되었습니다. 모든 아라비아 숫자를 "
            "제거하고 '여러/일부/다수' 등 정성적 표현으로 바꾸어 다시 작성하십시오. "
            "토큰(OBJ-1 등) 외에는 절대 숫자를 쓰지 마십시오."
        )
    return body


def _allowed_tokens(facts: LLMFacts) -> set[str]:
    """All anonymization tokens present in ``facts`` (these legitimately have digits).

    Collected from every place :mod:`sanitize` mints a token: object/owner tokens
    on each fact type plus the conjunction primary/secondary token pair.
    """
    tokens: set[str] = set()
    for o in facts.objects:
        tokens.add(o.token)
    for c in facts.conjunctions:
        tokens.add(c.primary_token)
        tokens.add(c.secondary_token)
    for m in facts.maneuvers:
        tokens.add(m.token)
    for r in facts.reentries:
        tokens.add(r.token)
    for c in facts.country_breakdown:
        tokens.add(c.token)
    for s in facts.time_series:
        tokens.add(s.token)
    return tokens


def _has_stray_digit(prose: str, allowed_tokens: set[str]) -> bool:
    """True if ``prose`` contains a digit that is NOT part of an allowed token.

    We blank out every allowed token first (longest-first so "OBJ-11" is removed
    before "OBJ-1" can match its prefix), then scan the remainder for any digit.
    A surviving digit means a hallucinated figure → reject.
    """
    residue = prose
    for token in sorted(allowed_tokens, key=len, reverse=True):
        residue = residue.replace(token, " ")
    return bool(_DIGIT_RE.search(residue))


def _deanonymize(prose: str, alias_map: dict[str, str]) -> str:
    """Replace tokens with their originals (longest-first to avoid prefix clashes)."""
    out = prose
    for token in sorted(alias_map, key=len, reverse=True):
        out = out.replace(token, alias_map[token])
    return out


def _extract_content(response: Any) -> str:
    """Pull the assistant text from a chat-completion response.

    Access path confirmed against openai 2.43: ``response.choices[0].message.content``.
    """
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise SectionError(f"malformed LLM response: {exc!r}") from exc
    if not content:
        raise SectionError("empty LLM response content")
    return content


def write_section(
    section: str,
    facts: LLMFacts,
    *,
    client: openai.OpenAI,
    settings: Settings,
    alias_map: dict[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Generate one de-anonymized Korean prose section.

    Strategy per *generation attempt* (a generation = one transient-retry loop +
    one guard check):

    * Up to ``settings.report_llm_max_retries`` retries on transient provider
      errors, exponential backoff (``0.5 * 2**n`` seconds; ``sleep`` injectable
      so tests pass a no-op).
    * The produced (still-tokenized) text is run through the no-numerals guard.
      A violation triggers ONE stricter re-generation; a second violation raises.

    ``alias_map`` (token -> original) drives de-anonymization, applied ONLY after
    the guard passes.
    """
    alias_map = alias_map or {}
    allowed = _allowed_tokens(facts)

    for strict in (False, True):
        raw = _generate_with_retries(
            section, facts, client=client, settings=settings, strict=strict, sleep=sleep
        )
        if not _has_stray_digit(raw, allowed):
            return _deanonymize(raw, alias_map)
        # Guard rejected: loop once more with the stricter prompt (strict=True).

    raise SectionError(
        f"section '{section}' kept emitting stray digits after a stricter retry"
    )


def _generate_with_retries(
    section: str,
    facts: LLMFacts,
    *,
    client: openai.OpenAI,
    settings: Settings,
    strict: bool,
    sleep: Callable[[float], None],
) -> str:
    """One transient-retry loop returning the RAW (tokenized) prose."""
    messages = [
        {"role": "system", "content": _system_prompt(section)},
        {"role": "user", "content": _user_prompt(section, facts, strict=strict)},
    ]
    attempts = settings.report_llm_max_retries + 1  # initial try + N retries
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(
                model=settings.report_llm_model,
                messages=messages,
            )
            return _extract_content(response)
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            sleep(0.5 * (2**attempt))
    raise SectionError(
        f"section '{section}' failed after {attempts} attempt(s): {type(last_exc).__name__}"
    ) from last_exc


def write_report_prose(
    sanitize_result: SanitizeResult,
    *,
    client: openai.OpenAI | None = None,
    settings: Settings | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    """Generate every prose section, returning ``{section_name: prose}``.

    ``client`` / ``settings`` are injectable for tests; in production they are
    built from the environment. Any section that cannot be produced within budget
    propagates its :class:`SectionError`.
    """
    settings = settings or get_settings()
    client = client or build_client(settings)
    facts = sanitize_result.facts
    alias_map = sanitize_result.alias_map
    return {
        section: write_section(
            section, facts, client=client, settings=settings, alias_map=alias_map, sleep=sleep
        )
        for section in SECTIONS
    }
