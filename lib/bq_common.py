"""Shared project/store/spec resolution for black-qat."""
import json
from pathlib import Path
from typing import Mapping

TESTER_AGENT_TYPES = frozenset({"black-qat-tester", "black-qat:black-qat-tester"})

CONFIG_NAME = "black-qat.config.json"
DEFAULT_SPEC = "docs/black-qat/spec.md"


def find_root(cwd: str) -> Path:
    start = Path(cwd)
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def load_config(root: Path) -> dict:
    try:
        data = json.loads((root / CONFIG_NAME).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _config_str(root: Path, key: str):
    value = load_config(root).get(key)
    return value if isinstance(value, str) and value else None


def project_name(root: Path) -> str:
    return _config_str(root, "project") or root.name


def store_home(env: Mapping[str, str]) -> Path:
    if env.get("BQ_HOME"):
        return Path(env["BQ_HOME"])
    return Path(env.get("HOME", "~")).expanduser() / ".black-qat"


def store_dir(root: Path, env: Mapping[str, str]) -> Path:
    return store_home(env) / project_name(root)


def spec_path(root: Path) -> Path:
    return root / (_config_str(root, "specPath") or DEFAULT_SPEC)
