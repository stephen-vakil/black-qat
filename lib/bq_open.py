"""Human opener: shows the hidden suite's readable files in the user's viewer."""
import subprocess
import sys
from typing import Mapping

import bq_common
from bq_run import no_suite_message

READABLE_FILES = ("SCENARIOS.md", "GAPS.md", "CHANGELOG.md", ".last/summary.txt")


def main(argv, env: Mapping[str, str], cwd: str) -> int:
    root = bq_common.find_root(cwd)
    store = bq_common.store_dir(root, env)
    if not store.is_dir():
        print(no_suite_message(bq_common.project_name(root)))
        return 2

    cmd = env.get("BQ_OPEN_CMD") or ("open" if sys.platform == "darwin" else "xdg-open")
    opened = 0
    for rel in READABLE_FILES:
        path = store / rel
        if path.is_file():
            subprocess.run([cmd, str(path)])
            opened += 1
    print("black-qat: opened %d file(s) from %s" % (opened, store))
    return 0
