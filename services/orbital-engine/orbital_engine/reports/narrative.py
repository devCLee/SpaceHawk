"""LLM narrative generation for the daily report's Korean prose sections.

The deterministic template renders every *figure* (counts, distances, dates).
This module asks an external, OpenAI-COMPATIBLE LLM to write only the
*qualitative* prose for §6 일일 분석 내용 and §7 대응 작전 추진 내용 — returning
the typed :class:`~orbital_engine.reports.schemas.ReportProse` contract:

    analysis_items : list[AnalysisItem]   each = detail (상세 분석 내용)
                                          + cause_forecast (원인 및 예상 분석)
    response_ops   : list[str]            대응 작전 추진 내용 항목

Two hard invariants protect the boundary:

1. **Anonymized input.** The LLM is shown only the sanitized :class:`LLMFacts`
   (see :mod:`orbital_engine.reports.sanitize`), where every individual object
   identity is an opaque token ("OBJ-1", "OBJ-2"). Country codes/names are the
   public subject of the report and are shown in clear. The LLM never sees
   catalog object ids/names.

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

import json
import random
import re
import time
from collections.abc import Callable
from typing import Any

import openai

from orbital_engine.config import Settings, get_settings
from orbital_engine.reports.sanitize import LLMFacts, SanitizeResult
from orbital_engine.reports.schemas import AnalysisItem, ReportProse

# Provider errors worth retrying: explicit rate-limit, transient connection/
# timeout, and transient server-side 5xx. RateLimitError + InternalServerError
# subclass APIStatusError; APITimeoutError / APIConnectionError subclass APIError.
# InternalServerError covers the free-tier "503 high demand" (UNAVAILABLE) that
# Gemini returns under load — transient, so retry it. We catch this narrow set,
# NOT every APIError (a 400 bad-request must not be retried).
_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

# A "digit not inside an allowed token" — used by the no-numerals guard after the
# allowed tokens have been removed from the text.
_DIGIT_RE = re.compile(r"[0-9]")

# How many §6 analysis items we ask for. Kept short (a focused report reads a few
# salient findings, not an exhaustive list); the model decides how many of the
# available slots the day's facts actually warrant.
_MAX_ANALYSIS_ITEMS = 4
_MAX_RESPONSE_OPS = 4

# Transient-retry backoff: exponential (base * 2**n) but CAPPED so a large retry
# budget doesn't blow up to minutes per sleep, plus random jitter so concurrent
# jobs don't hammer an overloaded free tier in lockstep.
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0
_BACKOFF_JITTER_S = 0.75


class SectionError(RuntimeError):
    """The report prose could not be generated within the configured budget.

    Raised on retry exhaustion, timeout, or a persistent no-numerals violation.
    """


def build_client(settings: Settings) -> openai.OpenAI:
    """Construct an OpenAI-compatible client from settings.

    ``max_retries=0`` so retry/backoff is owned by :func:`write_report_prose`
    (the SDK's own retry layer would otherwise hide attempts from our budget and
    our tests). The free provider is selected purely by ``base_url``.
    """
    return openai.OpenAI(
        api_key=settings.report_llm_api_key,
        base_url=settings.report_llm_base_url,
        timeout=settings.report_llm_timeout_s,
        max_retries=0,
    )


def _system_prompt() -> str:
    return (
        "당신은 한국 우주영역인식(SDA) 일일 보고서의 서술형 문장을 작성하는 전문 분석관입니다. "
        "'일일 분석 내용'(분석 항목 목록)과 '대응 작전 추진 내용'(대응 작전 목록)을 작성합니다.\n"
        "반드시 다음 규칙을 지키십시오:\n"
        "1. 정성적(서술형) 한국어 문장만 작성합니다. 군더더기 없는 공식 보고서 문체를 사용합니다.\n"
        "2. 개별 객체(위성/잔해)는 오직 토큰으로만 지칭합니다 (예: OBJ-1, OBJ-2). "
        "실제 명칭/식별번호를 추측하지 마십시오. 국가명(북한/중국/러시아/일본 등)은 그대로 사용해도 됩니다.\n"
        "3. 어떤 숫자(아라비아 숫자)도 쓰지 마십시오. 건수·거리·확률·날짜·시각 등 모든 수치는 "
        "보고서의 다른 곳(표/그래프)에서 자동으로 채워지므로 문장에 숫자를 넣으면 안 됩니다. "
        "'여러', '일부', '다수', '소수' 같은 정성적 표현만 사용하십시오.\n"
        "4. 토큰(OBJ-1 등) 안의 숫자는 식별자의 일부이므로 그대로 사용해도 됩니다.\n"
        "5. 반드시 아래 형식의 JSON 객체 하나만 출력하십시오. JSON 외의 텍스트는 출력하지 마십시오.\n"
        '   {"analysis_items": [{"detail": "상세 분석 내용", "cause_forecast": "원인 및 예상 분석"}], '
        '"response_ops": ["대응 작전 추진 내용 항목"]}'
    )


def _user_prompt(facts: LLMFacts, *, strict: bool = False) -> str:
    facts_json = facts.model_dump_json()
    body = (
        "다음은 오늘 보고서의 익명화된 사실 데이터(JSON)입니다. 이를 근거로 '일일 분석 내용'과 "
        f"'대응 작전 추진 내용'을 한국어로 작성하십시오. '일일 분석 내용'은 최대 {_MAX_ANALYSIS_ITEMS}개의 "
        "분석 항목으로 구성하되, 사실 데이터가 뒷받침하는 만큼만(근접/충돌, 주목할 통과, 잔해 위험 등) "
        f"작성하십시오. '대응 작전 추진 내용'은 최대 {_MAX_RESPONSE_OPS}개의 항목으로 작성하십시오. "
        "개별 객체는 토큰으로만 지칭하고(국가명은 그대로), 문장에는 어떤 숫자도 포함하지 마십시오. "
        f"앞서 지정한 JSON 형식 하나만 출력하십시오.\n\n사실 데이터:\n{facts_json}"
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

    Collected from every place :mod:`sanitize` mints a token: the per-pass
    satellite token, the conjunction primary/secondary token pair, and the
    high-risk debris token.
    """
    tokens: set[str] = set()
    for ca in facts.country_activity:
        for p in ca.passes:
            tokens.add(p.token)
    for c in facts.conjunctions:
        tokens.add(c.primary_token)
        tokens.add(c.secondary_token)
    for d in facts.high_risk_debris:
        tokens.add(d.token)
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


def _parse_prose(raw: str) -> ReportProse:
    """Parse the model's raw JSON into a (still-tokenized) :class:`ReportProse`.

    Tolerates a fenced ```json block by extracting the first ``{...}`` object.
    Raises :class:`SectionError` on anything that is not the expected shape.
    """
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SectionError("LLM response did not contain a JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise SectionError(f"LLM response was not valid JSON: {exc!r}") from exc
    try:
        items = [
            AnalysisItem(detail=str(it["detail"]), cause_forecast=str(it["cause_forecast"]))
            for it in data.get("analysis_items", [])
        ]
        response_ops = [str(op) for op in data.get("response_ops", [])]
    except (TypeError, KeyError) as exc:
        raise SectionError(f"LLM response had an unexpected shape: {exc!r}") from exc
    return ReportProse(analysis_items=items, response_ops=response_ops)


def _prose_text(prose: ReportProse) -> str:
    """Flatten all prose strings into one blob for the no-numerals guard."""
    parts: list[str] = []
    for item in prose.analysis_items:
        parts.append(item.detail)
        parts.append(item.cause_forecast)
    parts.extend(prose.response_ops)
    return "\n".join(parts)


def _deanonymize_prose(prose: ReportProse, alias_map: dict[str, str]) -> ReportProse:
    """De-anonymize every prose string in ``prose`` via ``alias_map``."""
    return ReportProse(
        analysis_items=[
            AnalysisItem(
                detail=_deanonymize(item.detail, alias_map),
                cause_forecast=_deanonymize(item.cause_forecast, alias_map),
            )
            for item in prose.analysis_items
        ],
        response_ops=[_deanonymize(op, alias_map) for op in prose.response_ops],
    )


def _generate_with_retries(
    facts: LLMFacts,
    *,
    client: openai.OpenAI,
    settings: Settings,
    strict: bool,
    sleep: Callable[[float], None],
) -> str:
    """One transient-retry loop returning the RAW (tokenized) JSON string."""
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _user_prompt(facts, strict=strict)},
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
            delay = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_CAP_S)
            sleep(delay + random.uniform(0.0, _BACKOFF_JITTER_S))
    raise SectionError(
        f"report prose failed after {attempts} attempt(s): {type(last_exc).__name__}"
    ) from last_exc


def write_report_prose(
    sanitize_result: SanitizeResult,
    *,
    client: openai.OpenAI | None = None,
    settings: Settings | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ReportProse:
    """Generate the §6 / §7 Korean prose, returning a typed :class:`ReportProse`.

    ``client`` / ``settings`` are injectable for tests; in production they are
    built from the environment.

    Strategy (one generation = one transient-retry loop + one guard check):

    * Up to ``settings.report_llm_max_retries`` retries on transient provider
      errors (the free Gemini tier's intermittent 503 UNAVAILABLE included),
      exponential backoff capped at ``_BACKOFF_CAP_S`` with jitter (``sleep``
      injectable so tests pass a no-op).
    * The produced (still-tokenized) prose is run through the no-numerals guard
      over ALL prose strings. A violation triggers ONE stricter re-generation;
      a second violation raises :class:`SectionError`.

    The ``alias_map`` (token -> original) drives de-anonymization, applied ONLY
    after the guard passes. An empty-facts payload yields a minimal/empty
    ``ReportProse`` (whatever the model returns, typically empty lists).
    """
    settings = settings or get_settings()
    client = client or build_client(settings)
    facts = sanitize_result.facts
    alias_map = sanitize_result.alias_map
    allowed = _allowed_tokens(facts)

    for strict in (False, True):
        raw = _generate_with_retries(
            facts, client=client, settings=settings, strict=strict, sleep=sleep
        )
        prose = _parse_prose(raw)
        if not _has_stray_digit(_prose_text(prose), allowed):
            return _deanonymize_prose(prose, alias_map)
        # Guard rejected: loop once more with the stricter prompt (strict=True).

    raise SectionError("report prose kept emitting stray digits after a stricter retry")
