"""PreToolUse guard: hides the black-qat suite store from every agent but its tester."""
import os
import re
from pathlib import Path
from typing import Mapping, Optional

import report
from bq_common import TESTER_AGENT_TYPES, find_root, home_root, spec_path, store_home

TEXT_KEYS = ("file_path", "notebook_path", "path", "pattern", "command", "glob")
PATH_KEYS = ("file_path", "notebook_path", "path")
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
RUNNER_RE = re.compile(r"\bbq-(run|open)\b")

DENY_STORE = ("black-qat: the hidden test suite is off-limits to this agent. "
              "Humans can review it with /black-qat:open.")
DENY_TESTER_WRITE = "black-qat: the tester may only write in the suite store or the spec file"
DENY_DISPATCH = "black-qat: only the root session may dispatch the black-qat tester"
DENY_RUNNER = "black-qat: only the root session may run the black-qat runner"


def _resolve(raw: str, cwd: str) -> str:
    return os.path.realpath(os.path.join(cwd, os.path.expanduser(raw)))


def _under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def _tester_write_denied(tool_input: dict, cwd: str, env: Mapping[str, str]) -> bool:
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return True
    target = _resolve(raw, cwd)
    home = store_home(env)
    if _under(target, os.path.realpath(home)):
        return False
    return target != os.path.realpath(spec_path(home_root(find_root(cwd))))


def _references_store(tool_input: dict, cwd: str, env: Mapping[str, str]) -> bool:
    home = str(store_home(env)).lower()
    real_home = os.path.realpath(str(store_home(env))).lower()
    needles = (".black-qat", home, real_home)
    candidates = []
    for key in TEXT_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str):
            continue
        candidates.append(value)
        if key in PATH_KEYS and value:
            candidates.append(_resolve(value, cwd))
    return any(n in c.lower() for c in candidates for n in needles)


def decide(event: dict, env: Mapping[str, str]) -> Optional[str]:
    """Return a deny reason, or None to allow. Fails open on any error."""
    try:
        tool = event.get("tool_name")
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        cwd = event.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()

        if (tool in ("Agent", "Task") and event.get("agent_id")
                and tool_input.get("subagent_type") in TESTER_AGENT_TYPES):
            return DENY_DISPATCH
        if event.get("agent_type") in TESTER_AGENT_TYPES:
            if tool == "SubagentHandback":
                return report.handback_decision(event, env)
            if tool in WRITE_TOOLS and _tester_write_denied(tool_input, cwd, env):
                return DENY_TESTER_WRITE
            return None
        if _references_store(tool_input, cwd, env):
            return DENY_STORE
        command = tool_input.get("command")
        if (event.get("agent_id") and tool == "Bash" and isinstance(command, str)
                and RUNNER_RE.search(command)):
            return DENY_RUNNER
        return None
    except Exception:
        return None
