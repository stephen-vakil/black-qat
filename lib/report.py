"""Report contract: the only shapes the tester's final report may take.

The tester's report reaches the calling session verbatim, so anything beyond
the contract (scenario descriptions, test names, extra prose) leaks the hidden
suite. Hooks bounce a report that doesn't match and make the tester resend it.
"""
import re
from pathlib import Path
from typing import List, Mapping, Optional

from bq_common import TESTER_AGENT_TYPES, store_home

ID = re.compile(r"\bBQ-\d+")
COUNTS = re.compile(r"\d+ passed, \d+ failed(, \d+ skipped)?")
ABS_PATH = re.compile(r"(/|[A-Za-z]:\\)\S.*")
SKIP_LINE = re.compile(r"skipped: \S.*")
ITEM = re.compile(r"- \[(proposed|inferred)\] \S.*")
AMBIGUITY = re.compile(r"- \S.*")
TRIAGE_HEAD = re.compile(
    r"BQ-\d+ — (implementation bug|spec ambiguity"
    r"|test defect \(fixed, logged in CHANGELOG\.md\))")

SHAPES = """\
BLOCKED: <one line>
TESTS_BLOCKED: <one line>   (or TESTS_BLOCKED, then one reason line)
SPEC_READY / <spec path> / Needs decision: none   (or Needs decision: then "- [proposed] ..." / "- [inferred] ..." lines)
SCENARIOS_READY / <N> scenarios / Review with /black-qat:open / New ambiguities: none   (or New ambiguities: then "- ..." lines, no IDs)
TESTS_READY / <P> passed, <F> failed[, <S> skipped] / then only "skipped: <reason>" lines
TRIAGE_DONE / then "<ID> — <class>" lines, each followed by indented body lines with no IDs"""


def _no_ids(lines: List[str], what: str) -> Optional[str]:
    for line in lines:
        if ID.search(line):
            return "scenario ID in %s" % what
    return None


def _list_tail(lines: List[str], header: str, item: re.Pattern, what: str):
    if not lines:
        return "missing '%s' line" % header
    if lines[0] == header + " none":
        return None if len(lines) == 1 else "extra lines after '%s none'" % header
    if lines[0] != header:
        return "expected '%s'" % header
    for line in lines[1:]:
        if not item.fullmatch(line):
            return "unexpected line in %s: only list items allowed" % what
    return _no_ids(lines[1:], what)


def _blocked(lines):
    first = lines[0]
    if first.startswith("BLOCKED:"):
        return None if len(lines) == 1 else "BLOCKED must be one line"
    if first.startswith("TESTS_BLOCKED:"):
        return None if len(lines) == 1 else "TESTS_BLOCKED must be one line"
    return None if len(lines) == 2 else "TESTS_BLOCKED takes exactly one reason line"


def _spec(lines):
    if len(lines) < 3:
        return "SPEC_READY needs the spec path and a Needs decision line"
    if not ABS_PATH.fullmatch(lines[1]) or ID.search(lines[1]):
        return "second line must be the absolute spec path, nothing else"
    return _list_tail(lines[2:], "Needs decision:", ITEM, "Needs decision")


def _scenarios(lines):
    if len(lines) < 4:
        return "SCENARIOS_READY needs count, review line and New ambiguities"
    if not re.fullmatch(r"\d+ scenarios?", lines[1]):
        return "second line must be '<N> scenarios'"
    if lines[2] != "Review with /black-qat:open":
        return "third line must be 'Review with /black-qat:open'"
    return _list_tail(lines[3:], "New ambiguities:", AMBIGUITY, "New ambiguities")


def _tests(lines):
    if len(lines) < 2 or not COUNTS.fullmatch(lines[1]):
        return "second line must be '<P> passed, <F> failed[, <S> skipped]'"
    for line in lines[2:]:
        if not SKIP_LINE.fullmatch(line):
            return "only counts and 'skipped: <reason>' lines allowed"
    return _no_ids(lines[2:], "skip reason")


def _triage(raw_lines):
    items = 0
    for line in raw_lines[1:]:
        if not line.strip():
            continue
        if line[0].isspace():
            if not items:
                return "body before any '<ID> — <class>' line"
            if ID.search(line):
                return "scenario ID in a report body"
        elif TRIAGE_HEAD.fullmatch(line.rstrip()):
            items += 1
        else:
            return "unexpected line: only '<ID> — <class>' lines and indented bodies"
    return None if items else "TRIAGE_DONE with no items"


HANDLERS = {"SPEC_READY": _spec, "SCENARIOS_READY": _scenarios,
            "TESTS_READY": _tests}


def check(message) -> Optional[str]:
    """None if `message` is a valid report, else a short description of the problem."""
    if not isinstance(message, str):
        return "no report text"
    raw = message.strip("\n").split("\n")
    while raw and not raw[0].strip():
        raw.pop(0)
    if not raw:
        return "empty report"
    raw[0] = raw[0].strip()
    lines = [l.strip() for l in raw if l.strip()]
    first = lines[0]
    if first == "TRIAGE_DONE":
        return _triage(raw)
    if first.startswith(("BLOCKED:", "TESTS_BLOCKED")):
        return _blocked(lines)
    handler = HANDLERS.get(first)
    if handler is None:
        return "first line must be a status word (e.g. TESTS_READY), with no prose before it"
    return handler(lines)


def bounce(problem: str) -> str:
    return ("black-qat: your final report breaks the report contract (%s). It "
            "reaches the caller verbatim, so it must be exactly one of these "
            "shapes and nothing else: no scenario descriptions, test names, "
            "assertions or extra prose.\n%s\nResend only the report." % (problem, SHAPES))


def _marker(event: dict, env: Mapping[str, str]) -> Optional[Path]:
    agent_id = event.get("agent_id")
    if not isinstance(agent_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", agent_id):
        return None
    return store_home(env) / ".handbacks" / agent_id


def handback_decision(event: dict, env: Mapping[str, str]) -> Optional[str]:
    """PreToolUse on the tester's SubagentHandback: deny a report that breaks
    the contract. A clean one leaves a one-use marker so SubagentStop doesn't
    re-check the closing text that follows a delivered handback."""
    tool_input = event.get("tool_input") or {}
    problem = check(tool_input.get("message"))
    if problem:
        return bounce(problem)
    marker = _marker(event, env)
    if marker:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    return None


def stop_decision(event: dict, env: Mapping[str, str]) -> Optional[str]:
    """SubagentStop: a block reason if the tester's final message breaks the
    contract, else None. Fails open on errors."""
    try:
        if event.get("agent_type") not in TESTER_AGENT_TYPES:
            return None
        marker = _marker(event, env)
        if marker and marker.exists():
            marker.unlink()
            return None
        problem = check(event.get("last_assistant_message"))
        return bounce(problem) if problem else None
    except Exception:
        return None
