from decimal import Decimal

import pytest

from funding_story_ai.config import RuntimeSettings


def test_settings_require_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        RuntimeSettings.from_env()


def test_settings_allow_missing_project_for_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert RuntimeSettings.from_env(require_project=False).project_id == ""


def test_settings_read_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GCP_SPEND_LIMIT_KRW", "25000")
    assert RuntimeSettings.from_env().spend_limit_krw == Decimal("25000")


def test_settings_use_conservative_budget_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.delenv("GCP_SPEND_LIMIT_KRW", raising=False)
    assert RuntimeSettings.from_env().spend_limit_krw == Decimal("10000")
