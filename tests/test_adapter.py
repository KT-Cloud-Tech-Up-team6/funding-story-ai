from decimal import Decimal
from types import SimpleNamespace

import pytest

from funding_story_ai.adapter import GeminiAdapter
from funding_story_ai.config import RuntimeSettings
from funding_story_ai.pricing import ModelPrice, PricingCatalog
from funding_story_ai.usage import UsageLedger


class AccessError(RuntimeError):
    code = 503


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.models = []

    def generate_content(self, *, model, contents, config):
        self.models.append(model)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response():
    return SimpleNamespace(
        text='{"status":"ok"}',
        parsed={"status": "ok"},
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=3,
            thoughts_token_count=2,
            cached_content_token_count=0,
        ),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))],
    )


def adapter(tmp_path, outcomes, attempts=5):
    settings = RuntimeSettings(
        project_id="test-project",
        primary_access_attempts=attempts,
        spend_limit_krw=Decimal("1000"),
    )
    pricing = PricingCatalog(
        {
            settings.primary_model: ModelPrice(Decimal("1"), Decimal("1"), "test"),
            settings.fallback_model: ModelPrice(Decimal("1"), Decimal("1"), "test"),
        }
    )
    ledger = UsageLedger(tmp_path / "usage.jsonl", Decimal("1000"), Decimal("1"), pricing)
    models = FakeModels(outcomes)
    return GeminiAdapter(
        settings,
        ledger,
        client=SimpleNamespace(models=models),
        sleep=lambda _: None,
    ), models


def test_success_uses_primary(tmp_path) -> None:
    target, models = adapter(tmp_path, [response()])
    result = target.generate_json(prompt="test", response_schema={"type": "object"})
    assert result.model == "gemini-3.7-flash"
    assert result.usage.thinking_tokens == 2
    assert models.models == ["gemini-3.7-flash"]


def test_fallback_after_five_access_errors(tmp_path) -> None:
    target, models = adapter(tmp_path, [AccessError()] * 5 + [response()])
    result = target.generate_json(prompt="test", response_schema={"type": "object"})
    assert result.model == "gemini-3.6-flash"
    assert result.attempts == 6
    assert models.models == ["gemini-3.7-flash"] * 5 + ["gemini-3.6-flash"]


def test_non_access_error_does_not_fallback(tmp_path) -> None:
    target, models = adapter(tmp_path, [ValueError("invalid response")])
    with pytest.raises(ValueError, match="invalid response"):
        target.generate_json(prompt="test", response_schema={"type": "object"})
    assert models.models == ["gemini-3.7-flash"]
