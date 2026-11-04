import pytest

from core.settings import ApplicationMode, ConfigError, load_settings


def test_default_settings_file_is_valid(monkeypatch):
    monkeypatch.delenv("APPLICATION_MODE", raising=False)
    s = load_settings()
    assert s.timezone == "Asia/Kolkata"
    assert s.applications.mode == ApplicationMode.APPROVAL_REQUIRED
    assert s.scheduler.run_time == "09:00"
    assert sum(s.matching.weights.model_dump().values()) == 100


def test_env_overrides(settings_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("APPLICATION_MODE", "ASSISTED")
    monkeypatch.setenv("RESUME_PATH", str(tmp_path / "other.pdf"))
    s = settings_factory()
    assert s.applications.mode == ApplicationMode.ASSISTED
    assert s.resume_path == tmp_path / "other.pdf"


@pytest.mark.parametrize("override", [
    {"applications__mode": "YOLO"},
    {"scheduler__run_time": "25:00"},
    {"matching__categories__good": 90},
    {"llm__effort": "extreme"},
    {"unknown_section": {"x": 1}},
])
def test_invalid_settings_rejected(settings_factory, override):
    with pytest.raises(ConfigError):
        settings_factory(**override)


def test_missing_settings_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    p = tmp_path / "config" / "settings.yaml"
    p.parent.mkdir()
    p.write_text("candidate: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(p)
