import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import guard  # noqa: E402
import report  # noqa: E402

TESTER = "black-qat:black-qat-tester"
LEAKY = "TESTS_READY\n3 passed, 0 failed\nI checked that an empty title returns 400."
CLEAN = "TESTS_READY\n3 passed, 0 failed"
ROOT = Path(__file__).resolve().parent.parent

GOOD = [
    "BLOCKED: missing STORE",
    "TESTS_BLOCKED: spec changed since the register was written; run /black-qat:scenarios again and review",
    "TESTS_BLOCKED\nthe spec's How to run section doesn't say how to start the server",
    "SPEC_READY\n/r/docs/black-qat/spec.md\nNeeds decision: none",
    "SPEC_READY\n/r/docs/black-qat/spec.md\nNeeds decision:\n- [proposed] errors return JSON {error}\n- [inferred] names are case-insensitive",
    "SCENARIOS_READY\n24 scenarios\nReview with /black-qat:open\nNew ambiguities: none",
    "SCENARIOS_READY\n1 scenario\nReview with /black-qat:open\nNew ambiguities: none",
    "SCENARIOS_READY\n24 scenarios\nReview with /black-qat:open\nNew ambiguities:\n- the spec doesn't say what an empty title returns",
    "TESTS_READY\n0 passed, 24 failed",
    "TESTS_READY\n0 passed, 20 failed, 4 skipped\nskipped: needs ANTHROPIC_API_KEY",
    "\n  TESTS_READY\n3 passed, 0 failed\n\n",
    ("TRIAGE_DONE\n"
     "BQ-003 — implementation bug\n"
     "  Action/input: POST /items with title \"\"\n"
     "  Observed:     201 Created\n"
     "  Required:     400 with error \"title required\"\n"
     "  Spec section: Interface > POST /items\n"
     "\n"
     "BQ-007 — spec ambiguity\n"
     "  The spec doesn't say whether duplicate titles are allowed.\n"
     "BQ-009 — test defect (fixed, logged in CHANGELOG.md)"),
]

BAD = [
    ("", "empty"),
    ("All done! Here's what I tested:\nTESTS_READY\n3 passed, 0 failed", "prose before"),
    ("TESTS_READY\n3 passed, 0 failed\n\nScenarios covered:\n- BQ-001 checks empty title returns 400", "prose after"),
    ("TESTS_READY\n3 passed, 0 failed\nskipped: needs KEY for BQ-004", "ID in skip line"),
    ("TESTS_READY\nall good", "bad counts"),
    ("TESTS_BLOCKED\nline one\nline two", "multi-line blocked"),
    ("BLOCKED: x\nmore", "multi-line blocked"),
    ("SCENARIOS_READY\n24 scenarios\nReview with /black-qat:open\nNew ambiguities:\n- BQ-004 may be wrong", "ID in ambiguity"),
    ("SCENARIOS_READY\n24 scenarios\nReview with /black-qat:open\nNew ambiguities: none\nI wrote: 1. empty title returns 400", "extra line"),
    ("SCENARIOS_READY\n24 scenarios", "truncated"),
    ("SPEC_READY\n/r/spec.md\nNeeds decision:\nThe spec covers POST and GET.", "non-item line"),
    ("SPEC_READY\nI wrote tests for login\nNeeds decision: none", "second line not a path"),
    ("SPEC_READY\n/r/BQ-001-login.md\nNeeds decision: none", "ID in path line"),
    ("TRIAGE_DONE\nBQ-003 — implementation bug\n  Observed: the test BQ-003 asserts 400", "ID in body"),
    ("TRIAGE_DONE\nBQ-003 — implementation bug\nObserved: 201", "unindented body"),
    ("TRIAGE_DONE\nSummary: 1 bug", "bad header"),
    ("TRIAGE_DONE", "no items"),
]


class ReportTests(unittest.TestCase):
    def test_good_reports_pass(self):
        for message in GOOD:
            self.assertIsNone(report.check(message), message)

    def test_bad_reports_rejected(self):
        for message, why in BAD:
            problem = report.check(message)
            self.assertIsInstance(problem, str, why)
            self.assertTrue(problem, why)

    def test_non_string_rejected(self):
        self.assertIsInstance(report.check(None), str)

    def test_bounce_message_names_problem_and_shapes(self):
        text = report.bounce("prose after the counts")
        self.assertIn("prose after the counts", text)
        self.assertIn("TESTS_READY", text)
        self.assertIn("Resend", text)



class ReportHookTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.env = {"HOME": os.path.realpath(self._td.name)}

    def handback(self, message, agent_type=TESTER, agent_id="a1"):
        return guard.decide({"tool_name": "SubagentHandback",
                             "tool_input": {"message": message},
                             "agent_type": agent_type, "agent_id": agent_id,
                             "cwd": self._td.name}, self.env)

    def stop(self, message, agent_type=TESTER, agent_id="a1"):
        return report.stop_decision({"hook_event_name": "SubagentStop",
                                     "agent_type": agent_type, "agent_id": agent_id,
                                     "last_assistant_message": message}, self.env)

    def test_handback_leaky_report_denied_with_bounce(self):
        reason = self.handback(LEAKY)
        self.assertIn("report contract", reason)
        self.assertIn("Resend", reason)

    def test_handback_clean_report_allowed(self):
        self.assertIsNone(self.handback(CLEAN))

    def test_handback_from_other_agents_not_checked(self):
        self.assertIsNone(self.handback(LEAKY, agent_type="general-purpose"))

    def test_stop_checks_final_message(self):
        self.assertIn("report contract", self.stop(LEAKY))
        self.assertIsNone(self.stop(CLEAN))
        self.assertIsNone(self.stop(LEAKY, agent_type="Explore"))

    def test_stop_after_clean_handback_ignores_closing_text(self):
        self.assertIsNone(self.handback(CLEAN, agent_id="a2"))
        self.assertIsNone(self.stop("Done.", agent_id="a2"))
        # the marker is used once: a later stop is checked again
        self.assertIsNotNone(self.stop("Done.", agent_id="a2"))

    def test_stop_after_rejected_handback_still_checked(self):
        self.assertIsNotNone(self.handback(LEAKY, agent_id="a3"))
        self.assertIsNotNone(self.stop("Done.", agent_id="a3"))

    def test_stop_entry_point(self):
        event = {"hook_event_name": "SubagentStop", "agent_type": TESTER,
                 "agent_id": "a4", "last_assistant_message": LEAKY}
        proc = subprocess.run([sys.executable, str(ROOT / "hooks" / "report_stop.py")],
                              input=json.dumps(event), capture_output=True,
                              text=True, env=dict(os.environ, **self.env))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("report contract", out["reason"])
        proc = subprocess.run([sys.executable, str(ROOT / "hooks" / "report_stop.py")],
                              input="not json", capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
