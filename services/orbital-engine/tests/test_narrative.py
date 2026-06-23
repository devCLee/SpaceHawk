"""LLM narrative generation (HWPX pipeline T3) — mocked client, NO network.

These prove the prose generator's contract without any live call:

* success → de-anonymized Korean prose,
* transient errors (429 / timeout) → retried with backoff, then succeed or raise,
* the no-numerals guard rejects a stray digit (and a clean retry recovers),
* the guard ALLOWS digits that sit inside anonymization tokens (OBJ-1 …),
* tokens are replaced by their ``alias_map`` originals only after the guard.

The fake client mirrors the real ``client.chat.completions.create(model=, messages=)``
surface confirmed against openai 2.43; exceptions are the real SDK classes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import openai
import pytest

from orbital_engine.config import Settings
from orbital_engine.reports.narrative import (
    SectionError,
    write_report_prose,
    write_section,
)
from orbital_engine.reports.sanitize import (
    LLMConjunctionFact,
    LLMFacts,
    LLMObjectFact,
    SanitizeResult,
)

# --- fixtures: settings, facts, fake client -------------------------------


def _settings(max_retries: int = 4) -> Settings:
    # No api key / base_url needed: the client is injected, never built here.
    return Settings(report_llm_max_retries=max_retries, report_llm_model="test-model")


def _sanitize_result() -> SanitizeResult:
    """Two objects in one conjunction, mapping back to digit-bearing originals."""
    facts = LLMFacts(
        report_date=date(2026, 6, 20),
        objects=[
            LLMObjectFact(token="OBJ-1", regime="LEO", object_type="PAYLOAD"),
            LLMObjectFact(token="OBJ-2", regime="LEO", object_type="DEBRIS"),
        ],
        conjunctions=[
            LLMConjunctionFact(
                primary_token="OBJ-1",
                secondary_token="OBJ-2",
                miss_distance_km=0.4,
                probability=1e-4,
                tca=datetime(2026, 6, 20, 12, tzinfo=UTC),
                alert_level="HIGH",
            )
        ],
    )
    alias_map = {"OBJ-1": "SH:CAT:000025544", "OBJ-2": "1998-067A"}
    return SanitizeResult(facts=facts, alias_map=alias_map)


def _ok_response(content: str) -> SimpleNamespace:
    """Mimic ``ChatCompletion``: ``.choices[0].message.content``."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _rate_limit_error() -> openai.RateLimitError:
    req = httpx.Request("POST", "http://test")
    resp = httpx.Response(429, request=req)
    return openai.RateLimitError("rate limited", response=resp, body=None)


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "http://test"))


class FakeCompletions:
    """Records calls and replays a scripted sequence of results/exceptions."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[dict] = []

    def create(self, *, model: str, messages: list) -> object:
        self.calls.append({"model": model, "messages": messages})
        if not self._script:
            raise AssertionError("FakeCompletions called more times than scripted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    """Stand-in for ``openai.OpenAI`` exposing ``.chat.completions.create``."""

    def __init__(self, script: list) -> None:
        completions = FakeCompletions(script)
        self.chat = SimpleNamespace(completions=completions)
        self.completions = completions  # convenience handle for assertions


def _noop_sleep(_seconds: float) -> None:
    return None


# --- tests ----------------------------------------------------------------


def test_success_returns_deanonymized_prose() -> None:
    sr = _sanitize_result()
    client = FakeClient([_ok_response("OBJ-1과 OBJ-2의 근접이 관측되었습니다.")])

    out = write_section(
        "분석내용",
        sr.facts,
        client=client,
        settings=_settings(),
        alias_map=sr.alias_map,
        sleep=_noop_sleep,
    )

    # tokens replaced by their alias_map originals
    assert "SH:CAT:000025544" in out
    assert "1998-067A" in out
    assert "OBJ-1" not in out
    assert "OBJ-2" not in out
    assert client.completions.calls[0]["model"] == "test-model"


def test_rate_limit_then_success_is_retried() -> None:
    sr = _sanitize_result()
    client = FakeClient([
        _rate_limit_error(),
        _ok_response("OBJ-1 객체의 기동이 의심됩니다."),
    ])

    out = write_section(
        "개요", sr.facts, client=client, settings=_settings(), alias_map=sr.alias_map, sleep=_noop_sleep
    )

    assert "SH:CAT:000025544" in out
    assert len(client.completions.calls) == 2  # one failed, one succeeded


def test_retry_exhausted_raises_section_error() -> None:
    sr = _sanitize_result()
    # max_retries=2 => 3 attempts, all 429.
    client = FakeClient([_rate_limit_error(), _rate_limit_error(), _rate_limit_error()])

    with pytest.raises(SectionError):
        write_section(
            "개요",
            sr.facts,
            client=client,
            settings=_settings(max_retries=2),
            alias_map=sr.alias_map,
            sleep=_noop_sleep,
        )
    assert len(client.completions.calls) == 3


def test_timeout_error_raises_after_retries() -> None:
    sr = _sanitize_result()
    client = FakeClient([_timeout_error(), _timeout_error()])

    with pytest.raises(SectionError):
        write_section(
            "개요",
            sr.facts,
            client=client,
            settings=_settings(max_retries=1),  # 2 attempts
            alias_map=sr.alias_map,
            sleep=_noop_sleep,
        )
    assert len(client.completions.calls) == 2


def test_stray_digit_rejected_then_clean_retry_recovers() -> None:
    sr = _sanitize_result()
    # First generation has a bare digit ("총 5건") → rejected; the stricter
    # re-generation returns clean prose → success.
    client = FakeClient([
        _ok_response("총 5건의 근접이 있었습니다."),
        _ok_response("다수의 근접이 OBJ-1에서 관측되었습니다."),
    ])

    out = write_section(
        "분석내용",
        sr.facts,
        client=client,
        settings=_settings(),
        alias_map=sr.alias_map,
        sleep=_noop_sleep,
    )

    assert "SH:CAT:000025544" in out  # OBJ-1 de-anonymized
    assert len(client.completions.calls) == 2  # rejected once, recovered


def test_stray_digit_persists_raises_section_error() -> None:
    sr = _sanitize_result()
    # Both the initial and the stricter re-generation contain a stray digit.
    client = FakeClient([
        _ok_response("총 5건 관측."),
        _ok_response("거리는 3km 입니다."),
    ])

    with pytest.raises(SectionError):
        write_section(
            "분석내용",
            sr.facts,
            client=client,
            settings=_settings(),
            alias_map=sr.alias_map,
            sleep=_noop_sleep,
        )
    assert len(client.completions.calls) == 2  # one reject + one stricter reject


def test_guard_allows_digits_inside_tokens() -> None:
    sr = _sanitize_result()
    # Digits appear ONLY inside the allowed tokens → guard must pass (1 call).
    client = FakeClient([_ok_response("OBJ-1과 OBJ-2 근접")])

    out = write_section(
        "분석내용",
        sr.facts,
        client=client,
        settings=_settings(),
        alias_map=sr.alias_map,
        sleep=_noop_sleep,
    )

    assert len(client.completions.calls) == 1  # accepted on first try
    assert "SH:CAT:000025544" in out
    assert "1998-067A" in out


def test_write_report_prose_runs_all_sections() -> None:
    sr = _sanitize_result()
    # Three SECTIONS => three accepted calls.
    client = FakeClient([
        _ok_response("OBJ-1 관련 개요."),
        _ok_response("OBJ-2 관련 분석."),
        _ok_response("향후 OBJ-1 추적 예정."),
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert set(out.keys()) == {"개요", "분석내용", "향후추진"}
    assert all("OBJ-" not in v for v in out.values())  # all de-anonymized
    assert len(client.completions.calls) == 3
