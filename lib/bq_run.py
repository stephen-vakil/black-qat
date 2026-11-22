"""Summary-only suite runner: runs the hidden suite, prints one line."""
import argparse
import datetime
import json
import os
import subprocess
from pathlib import Path
from typing import Mapping

import bq_common

LAST_RUN_COLUMN = 5  # '| ID | Title | What it checks | Spec ref | Last run |'
REASON_MAX = 80
EXIT_PASS, EXIT_FAIL, EXIT_ERROR, EXIT_SKIPPED = 0, 1, 2, 3


def no_suite_message(name: str) -> str:
    return ("black-qat: no suite for project '%s'. "
            "Run /black-qat:scenarios and /black-qat:tests first." % name)


def _reason(value):
    """Normalise a skip reason to one short line, or None if unusable."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).replace("|", "/")[:REASON_MAX].strip()
    return text or None


def _load_results(path: Path):
    """Map scenario ID -> (status, reason); None if the file is unusable."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    results = {}
    for item in data:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or item.get("status") not in ("pass", "fail", "skip")):
            return None
        reason = None
        if item["status"] == "skip":
            reason = _reason(item.get("reason"))
            if reason is None:
                return None
        results[item["id"]] = (item["status"], reason)
    return results


def _summary(results) -> str:
    failed = sorted(i for i, (s, _) in results.items() if s == "fail")
    skipped = sorted(i for i, (s, _) in results.items() if s == "skip")
    passed = len(results) - len(failed) - len(skipped)
    line = "%d passed, %d failed" % (passed, len(failed))
    if failed:
        line += ": " + ", ".join(failed)
    if skipped:
        groups = {}  # reason -> IDs, in order of first ID
        for i in skipped:
            groups.setdefault(results[i][1], []).append(i)
        line += "; %d skipped: %s" % (len(skipped), ", ".join(
            "%s (%s)" % (", ".join(ids), reason)
            for reason, ids in groups.items()))
    return line


def _update_register(path: Path, results: Mapping[str, str], day: str) -> None:
    try:
        text = path.read_text()
    except OSError:
        return
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.startswith("| BQ-"):
            continue
        cells = line.split("|")  # ['', ' BQ-001 ', ..., ' Last run ', '']
        if len(cells) <= LAST_RUN_COLUMN + 1:
            continue
        result = results.get(cells[1].strip())
        if result:
            status, reason = result
            cell = "%s %s" % (status, day)
            if reason:
                cell += " (%s)" % reason
            cells[LAST_RUN_COLUMN] = " %s " % cell
            lines[i] = "|".join(cells)
    path.write_text("\n".join(lines))


def main(argv, env: Mapping[str, str], cwd: str) -> int:
    parser = argparse.ArgumentParser(prog="bq-run")
    parser.add_argument("--target")
    args = parser.parse_args(argv)

    root = bq_common.find_root(cwd)
    name = bq_common.project_name(root)
    store = bq_common.store_dir(root, env)

    try:
        suite = json.loads((store / "run.json").read_text())
        command = suite["command"]
        project_root = suite["projectRoot"]
    except (OSError, ValueError, KeyError, TypeError):
        print(no_suite_message(name))
        return EXIT_ERROR

    if os.path.realpath(project_root) != os.path.realpath(str(root)):
        print("black-qat: the suite for '%s' belongs to %s. Set \"project\" in "
              "black-qat.config.json to give this repo its own suite."
              % (name, project_root))
        return EXIT_ERROR

    target = args.target or str(root)
    last = store / ".last"
    last.mkdir(parents=True, exist_ok=True)
    results_path = last / "results.json"
    results_path.unlink(missing_ok=True)

    run_env = dict(env, BQ_TARGET=target, BQ_RESULTS=str(results_path))
    with open(last / "raw.log", "wb") as log:
        subprocess.run(command, shell=True, cwd=str(store), env=run_env,
                       stdout=log, stderr=subprocess.STDOUT)

    results = _load_results(results_path)
    if not results:
        print("black-qat: the suite did not produce readable results. "
              "The tester can inspect the raw log.")
        return EXIT_ERROR

    line = _summary(results)
    print(line)

    now = datetime.datetime.now()
    (last / "summary.txt").write_text("%s\n%s\n" % (line, now.isoformat()))
    _update_register(store / "SCENARIOS.md", results, now.date().isoformat())
    statuses = {s for s, _ in results.values()}
    if "fail" in statuses:
        return EXIT_FAIL
    return EXIT_SKIPPED if "skip" in statuses else EXIT_PASS
