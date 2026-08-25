from types import SimpleNamespace

import pytest

from funding_story_ai.adapter import GeminiAdapter
from funding_story_ai.config import RuntimeSettings


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
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))],
    )


def adapter(outcomes, attempts=5):
    settings = RuntimeSettings(
        project_id="test-project",
        primary_access_attempts=attempts,
    )
    models = FakeModels(outcomes)
    return GeminiAdapter(
        settings,
        client=SimpleNamespace(models=models),
        sleep=lambda _: None,
    ), models


def test_success_uses_primary() -> None:
    target, models = adapter([response()])
    result = target.generate_json(prompt="test", response_schema={"type": "object"})
    assert result.model == "gemini-3.7-flash"
    assert models.models == ["gemini-3.7-flash"]


def test_fallback_after_five_access_errors() -> None:
    target, models = adapter([AccessError()] * 5 + [response()])
    result = target.generate_json(prompt="test", response_schema={"type": "object"})
    assert result.model == "gemini-3.6-flash"
    assert models.models == ["gemini-3.7-flash"] * 5 + ["gemini-3.6-flash"]


def test_non_access_error_does_not_fallback() -> None:
    target, models = adapter([ValueError("invalid response")])
    with pytest.raises(ValueError, match="invalid response"):
        target.generate_json(prompt="test", response_schema={"type": "object"})
    assert models.models == ["gemini-3.7-flash"]
