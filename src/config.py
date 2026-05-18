#!/usr/bin/env python3
"""Warp config loader."""
import os
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG_PATH = ROOT / "config" / "config.yaml.example"

ENV_ALIASES = {
    "llm.providers": ("LLM_PROVIDER_ORDER", "LLM_PROVIDERS"),
}


def _load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _env_first(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None


def _load_yaml(path: Path) -> dict:
    if not path.exists() or yaml is None:
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


_load_env_file()
CONFIG_PATH = Path(_env_first("WARP_CONFIG", "AXSUPPORT_CONFIG") or ROOT / "config" / "config.yaml")
_CONFIG = _load_yaml(CONFIG_PATH) or _load_yaml(EXAMPLE_CONFIG_PATH)


def get(key: str, default=None):
    env_key = key.upper().replace(".", "_")
    env_keys = (*ENV_ALIASES.get(key, ()), env_key)
    value = _env_first(*env_keys)
    if value is not None:
        if isinstance(default, int):
            try:
                return int(value)
            except ValueError:
                return default
        if isinstance(default, float):
            try:
                return float(value)
            except ValueError:
                return default
        if isinstance(default, list):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
    cur = _CONFIG
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def all_config() -> dict:
    return _CONFIG
