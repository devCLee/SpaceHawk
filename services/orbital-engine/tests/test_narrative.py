"""LLM narrative generation (HWPX pipeline R5) — mocked client, NO network.

These prove the prose generator's contract without any live call:

* success → de-anonymized Korean :class:`ReportProse` (analysis_items + response_ops),
* transient errors (429 / timeout) → retried with backoff, then succeed or raise,
* the no-numerals guard rejects a stray digit (and a clean retry recovers),
* the guard ALLOWS digits that sit inside anonymization tokens (OBJ-1 …),
* tokens are replaced by their ``alias_map`` originals only after the guard,
* empty facts → a valid minimal ``ReportProse``.

The fake client mirrors the real ``client.chat.completions.create(model=, messages=)``
surface confirmed against openai 2.43; exceptions are the real SDK classes. The
model is asked for a JSON object, so the scripted responses are JSON strings.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import openai
import pytest

from orbital_engine.config import Settings
from orbital_engine.reports.narrative import (
    SectionError,
    write_report_prose,
)
from orbital_engine.reports.schemas import ReportProse
from orbital_engine.reports.sanitize import (
    LLMConjunctionFact,
    LLMCountryActivityFact,
    LLMFacts,
    LLMPassFact,
    SanitizeResult,
)

# --- fixtures: settings, facts, fake client -------------------------------


def _settings(max_retries: int = 4) -> Settings:
    # No api key / base_url needed: the client is injected, never built here.
    return Settings(report_llm_max_retries=max_retries, report_llm_model="test-model")


def _sanitize_result() -> SanitizeResult:
    """A pass + a conjunction, with tokens mapping to digit-bearing originals."""
    facts = LLMFacts(
        report_date=date(2026, 6, 20),
        country_activity=[
            LLMCountryActivityFact(
                country_code="NK",
                country_name="북한",
                pass_count=1,
                passes=[LLMPassFact(token="OBJ-1", closest_distance_km=512.3, elevation_deg=42.0)],
            )
        ],
        conjunctions=[
            LLMConjunctionFact(
                primary_token="OBJ-1",
                secondary_token="OBJ-2",
                distance_km=0.4,
                probability=1e-4,
                tca=datetime(2026, 6, 20, 12, tzinfo=UTC),
                risk_category="HIGH",
            )
        ],
    )
    alias_map = {"OBJ-1": "SH:CAT:000025544", "OBJ-2": "1998-067A"}
    return SanitizeResult(facts=facts, alias_map=alias_map)


def _prose_json(*, detail: str, cause: str, op: str) -> str:
    """A well-formed prose JSON payload the way the model is asked to reply."""
    return json.dumps(
        {
            "analysis_items": [{"detail": detail, "cause_forecast": cause}],
            "response_ops": [op],
        },
        ensure_ascii=False,
    )


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
    client = FakeClient([
        _ok_response(
            _prose_json(
                detail="OBJ-1과 OBJ-2의 근접이 관측되었습니다.",
                cause="향후 추가 관측이 필요합니다.",
                op="OBJ-1 추적 강화.",
            )
        )
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert isinstance(out, ReportProse)
    assert len(out.analysis_items) == 1
    blob = " ".join(
        [out.analysis_items[0].detail, out.analysis_items[0].cause_forecast, *out.response_ops]
    )
    # tokens replaced by their alias_map originals
    assert "SH:CAT:000025544" in blob
    assert "1998-067A" in blob
    assert "OBJ-1" not in blob
    assert "OBJ-2" not in blob
    assert client.completions.calls[0]["model"] == "test-model"


def test_rate_limit_then_success_is_retried() -> None:
    sr = _sanitize_result()
    client = FakeClient([
        _rate_limit_error(),
        _ok_response(
            _prose_json(detail="OBJ-1 객체의 기동이 의심됩니다.", cause="원인 분석.", op="감시 유지.")
        ),
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert "SH:CAT:000025544" in out.analysis_items[0].detail
    assert len(client.completions.calls) == 2  # one failed, one succeeded


def test_retry_exhausted_raises_section_error() -> None:
    sr = _sanitize_result()
    # max_retries=2 => 3 attempts, all 429.
    client = FakeClient([_rate_limit_error(), _rate_limit_error(), _rate_limit_error()])

    with pytest.raises(SectionError):
        write_report_prose(sr, client=client, settings=_settings(max_retries=2), sleep=_noop_sleep)
    assert len(client.completions.calls) == 3


def test_timeout_error_raises_after_retries() -> None:
    sr = _sanitize_result()
    client = FakeClient([_timeout_error(), _timeout_error()])

    with pytest.raises(SectionError):
        write_report_prose(sr, client=client, settings=_settings(max_retries=1), sleep=_noop_sleep)
    assert len(client.completions.calls) == 2


def test_stray_digit_rejected_then_clean_retry_recovers() -> None:
    sr = _sanitize_result()
    # First generation has a bare digit ("총 5건") → rejected; the stricter
    # re-generation returns clean prose → success.
    client = FakeClient([
        _ok_response(
            _prose_json(detail="총 5건의 근접이 있었습니다.", cause="원인.", op="대응.")
        ),
        _ok_response(
            _prose_json(detail="다수의 근접이 OBJ-1에서 관측되었습니다.", cause="원인.", op="대응.")
        ),
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert "SH:CAT:000025544" in out.analysis_items[0].detail  # OBJ-1 de-anonymized
    assert len(client.completions.calls) == 2  # rejected once, recovered


def test_stray_digit_persists_raises_section_error() -> None:
    sr = _sanitize_result()
    # Both the initial and the stricter re-generation contain a stray digit.
    client = FakeClient([
        _ok_response(_prose_json(detail="총 5건 관측.", cause="원인.", op="대응.")),
        _ok_response(_prose_json(detail="거리는 3km 입니다.", cause="원인.", op="대응.")),
    ])

    with pytest.raises(SectionError):
        write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)
    assert len(client.completions.calls) == 2  # one reject + one stricter reject


def test_guard_allows_digits_inside_tokens() -> None:
    sr = _sanitize_result()
    # Digits appear ONLY inside the allowed tokens → guard must pass (1 call).
    client = FakeClient([
        _ok_response(
            _prose_json(detail="OBJ-1과 OBJ-2 근접.", cause="OBJ-1 감시.", op="OBJ-2 추적.")
        )
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert len(client.completions.calls) == 1  # accepted on first try
    blob = " ".join(
        [out.analysis_items[0].detail, out.analysis_items[0].cause_forecast, *out.response_ops]
    )
    assert "SH:CAT:000025544" in blob
    assert "1998-067A" in blob


def test_empty_facts_yields_minimal_prose() -> None:
    sr = SanitizeResult(facts=LLMFacts(report_date=date(2026, 6, 20)), alias_map={})
    client = FakeClient([
        _ok_response(json.dumps({"analysis_items": [], "response_ops": []}))
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert isinstance(out, ReportProse)
    assert out.analysis_items == []
    assert out.response_ops == []
    assert len(client.completions.calls) == 1


def test_returns_multiple_analysis_items_and_response_ops() -> None:
    sr = _sanitize_result()
    client = FakeClient([
        _ok_response(
            json.dumps(
                {
                    "analysis_items": [
                        {"detail": "OBJ-1 근접 분석.", "cause_forecast": "지속 감시 필요."},
                        {"detail": "잔해 위험 증가.", "cause_forecast": "고도별 밀도 상승."},
                    ],
                    "response_ops": ["OBJ-2 추적 강화.", "대응 태세 유지."],
                },
                ensure_ascii=False,
            )
        )
    ])

    out = write_report_prose(sr, client=client, settings=_settings(), sleep=_noop_sleep)

    assert len(out.analysis_items) == 2
    assert len(out.response_ops) == 2
    assert all("OBJ-" not in i.detail for i in out.analysis_items)
    assert all("OBJ-" not in op for op in out.response_ops)
