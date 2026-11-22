#!/usr/bin/env python3
"""Hook entry point: SubagentStop for the tester. Blocks a final report that
breaks the report contract, so the tester must resend it."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

import report  # noqa: E402


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    reason = report.stop_decision(event, os.environ)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
