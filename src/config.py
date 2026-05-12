     1|#!/usr/bin/env python3
     2|"""Warp config loader."""
     3|import os
     4|from pathlib import Path
     5|
     6|try:
     7|    import yaml
     8|except Exception:  # pragma: no cover
     9|    yaml = None
    10|
    11|ROOT = Path(__file__).resolve().parents[1]
    12|CONFIG_PATH = Path(os.getenv("AXSUPPORT_CONFIG", ROOT / "config" / "config.yaml"))
    13|EXAMPLE_CONFIG_PATH = ROOT / "config" / "config.yaml.example"
    14|
    15|
    16|def _load_env_file() -> None:
    17|    env_path = ROOT / ".env"
    18|    if not env_path.exists():
    19|        return
    20|    for line in env_path.read_text(errors="ignore").splitlines():
    21|        line = line.strip()
    22|        if not line or line.startswith("#") or "=" not in line:
    23|            continue
    24|        key, value = line.split("=", 1)
    25|        os.environ.setdefault(key.strip(), value.strip())
    26|
    27|
    28|def _load_yaml(path: Path) -> dict:
    29|    if not path.exists() or yaml is None:
    30|        return {}
    31|    with path.open() as f:
    32|        return yaml.safe_load(f) or {}
    33|
    34|
    35|_load_env_file()
    36|_CONFIG = _load_yaml(CONFIG_PATH) or _load_yaml(EXAMPLE_CONFIG_PATH)
    37|
    38|
    39|def get(key: str, default=None):
    40|    env_key = key.upper().replace(".", "_")
    41|    if env_key in os.environ:
    42|        value = os.environ[env_key]
    43|        if isinstance(default, int):
    44|            try:
    45|                return int(value)
    46|            except ValueError:
    47|                return default
    48|        if isinstance(default, float):
    49|            try:
    50|                return float(value)
    51|            except ValueError:
    52|                return default
    53|        if isinstance(default, list):
    54|            return [item.strip() for item in value.split(",") if item.strip()]
    55|        return value
    56|    cur = _CONFIG
    57|    for part in key.split("."):
    58|        if not isinstance(cur, dict) or part not in cur:
    59|            return default
    60|        cur = cur[part]
    61|    return cur
    62|
    63|
    64|def all_config() -> dict:
    65|    return _CONFIG
    66|