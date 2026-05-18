import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "tools"))


def reload_config():
    import config

    return importlib.reload(config)


def reload_helpdesk_common():
    import helpdesk_common

    return importlib.reload(helpdesk_common)


def test_warp_config_env_overrides_legacy_alias(monkeypatch, tmp_path):
    warp_config = tmp_path / "warp.yaml"
    legacy_config = tmp_path / "legacy.yaml"
    warp_config.write_text("agent:\n  name: warp-env\n")
    legacy_config.write_text("agent:\n  name: legacy-env\n")

    monkeypatch.setenv("WARP_CONFIG", str(warp_config))
    monkeypatch.setenv("AXSUPPORT_CONFIG", str(legacy_config))

    config = reload_config()

    assert config.all_config()["agent"]["name"] == "warp-env"


def test_axsupport_config_alias_still_supported(monkeypatch, tmp_path):
    legacy_config = tmp_path / "legacy.yaml"
    legacy_config.write_text("agent:\n  name: legacy-env\n")

    monkeypatch.setenv("WARP_CONFIG", "")
    monkeypatch.setenv("AXSUPPORT_CONFIG", str(legacy_config))

    config = reload_config()

    assert config.all_config()["agent"]["name"] == "legacy-env"


def test_provider_order_uses_documented_env_before_alias(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_ORDER", "openrouter,openai")
    monkeypatch.setenv("LLM_PROVIDERS", "anthropic")

    config = reload_config()

    assert config.get("llm.providers", ["anthropic"]) == ["openrouter", "openai"]


def test_llm_providers_alias_still_supported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_ORDER", "")
    monkeypatch.setenv("LLM_PROVIDERS", "openai,anthropic")

    config = reload_config()

    assert config.get("llm.providers", ["anthropic"]) == ["openai", "anthropic"]


def test_warp_http_timeout_overrides_legacy_alias(monkeypatch):
    monkeypatch.setenv("WARP_HTTP_TIMEOUT", "45")
    monkeypatch.setenv("AXSUPPORT_HTTP_TIMEOUT", "5")

    helpdesk_common = reload_helpdesk_common()

    assert helpdesk_common.TIMEOUT == 45


def test_axsupport_http_timeout_alias_still_supported(monkeypatch):
    monkeypatch.setenv("WARP_HTTP_TIMEOUT", "")
    monkeypatch.setenv("AXSUPPORT_HTTP_TIMEOUT", "15")

    helpdesk_common = reload_helpdesk_common()

    assert helpdesk_common.TIMEOUT == 15
