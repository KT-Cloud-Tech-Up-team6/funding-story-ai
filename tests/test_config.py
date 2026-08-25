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


def test_settings_read_model_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GEMINI_PRIMARY_MODEL", "custom-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "custom-fallback")
    settings = RuntimeSettings.from_env()
    assert settings.primary_model == "custom-primary"
    assert settings.fallback_model == "custom-fallback"


def test_settings_use_default_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.delenv("GEMINI_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.primary_model == "gemini-3.7-flash"
    assert settings.fallback_model == "gemini-3.6-flash"
