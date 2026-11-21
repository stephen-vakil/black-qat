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


def no_suite_message(name: str) -> str:
    return ("black-qat: no suite for project '%s'. "
            "Run /black-qat:scenarios and /black-qat:tests first." % name)


def _load_results(path: Path):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    results = {}
    for item in data:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or item.get("status") not in ("pass", "fail")):
            return None
        results[item["id"]] = item["status"]
    return results


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
        status = results.get(cells[1].strip())
        if status:
            cells[LAST_RUN_COLUMN] = " %s %s " % (status, day)
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
        return 2

    if os.path.realpath(project_root) != os.path.realpath(str(root)):
        print("black-qat: the suite for '%s' belongs to %s. Set \"project\" in "
              "black-qat.config.json to give this repo its own suite."
              % (name, project_root))
        return 2

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
        return 2

    failed = sorted(i for i, s in results.items() if s == "fail")
    passed = len(results) - len(failed)
    line = "%d passed, %d failed" % (passed, len(failed))
    if failed:
        line += ": " + ", ".join(failed)
    print(line)

    now = datetime.datetime.now()
    (last / "summary.txt").write_text("%s\n%s\n" % (line, now.isoformat()))
    _update_register(store / "SCENARIOS.md", results, now.date().isoformat())
    return 1 if failed else 0
