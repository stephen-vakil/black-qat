import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB))

import bq_run  # noqa: E402

REGISTER = """# Scenarios

Some prose with | pipes | and BQ-001 mentioned.

| ID | Title | What it checks | Spec ref | Last run |
|----|-------|----------------|----------|----------|
| BQ-001 | First | checks a | s1 | never |
| BQ-002 | Second | checks b | s2 | pass 2020-01-01 |

Trailing prose.
"""


def pyc(code):
    return "python3 -c " + json.dumps(code)


def write_results(items):
    return pyc("import json,os;json.dump(%r,open(os.environ['BQ_RESULTS'],'w'))"
               % (items,))


class BqRunTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(os.path.realpath(self._td.name))
        self.repo = self.tmp / "myrepo"
        (self.repo / ".git").mkdir(parents=True)
        self.home = self.tmp / "home"
        self.env = dict(os.environ, BQ_HOME=str(self.home))
        self.store = self.home / "myrepo"

    def make_suite(self, command, project_root=None):
        self.store.mkdir(parents=True, exist_ok=True)
        (self.store / "run.json").write_text(json.dumps({
            "projectRoot": str(project_root or self.repo), "command": command}))

    def run_main(self, argv=()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bq_run.main(list(argv), self.env, str(self.repo))
        return code, out.getvalue()

    def test_no_suite(self):
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("black-qat: no suite for project 'myrepo'. "
                      "Run /black-qat:scenarios and /black-qat:tests first.", out)

    def test_all_pass(self):
        self.make_suite(write_results(
            [{"id": "BQ-00%d" % i, "status": "pass"} for i in (1, 2, 3)]))
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "3 passed, 0 failed")
        self.assertTrue((self.store / ".last" / "summary.txt").exists())

    def test_failures_listed(self):
        self.make_suite(write_results([
            {"id": "BQ-001", "status": "pass"},
            {"id": "BQ-003", "status": "fail"},
            {"id": "BQ-002", "status": "fail"}]))
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "1 passed, 2 failed: BQ-002, BQ-003")

    def test_output_hides_raw(self):
        code_str = ("import sys,json,os;print('SECRET-ASSERTION');"
                    "print('SECRET-ASSERTION',file=sys.stderr);"
                    "json.dump([{'id':'BQ-001','status':'fail'}],"
                    "open(os.environ['BQ_RESULTS'],'w'))")
        self.make_suite(pyc(code_str))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = self.run_main()
        self.assertNotIn("SECRET-ASSERTION", out)
        self.assertNotIn("SECRET-ASSERTION", err.getvalue())
        raw = (self.store / ".last" / "raw.log").read_text()
        self.assertIn("SECRET-ASSERTION", raw)

    def _target_command(self):
        return pyc("import json,os;"
                   "open(os.path.join(os.path.dirname(os.environ['BQ_RESULTS']),"
                   "'target.txt'),'w').write(os.environ['BQ_TARGET']);"
                   "json.dump([{'id':'BQ-001','status':'pass'}],"
                   "open(os.environ['BQ_RESULTS'],'w'))")

    def test_target_passed_through(self):
        self.make_suite(self._target_command())
        self.run_main(["--target", "/some/path"])
        self.assertEqual((self.store / ".last" / "target.txt").read_text(),
                         "/some/path")

    def test_target_defaults_to_repo_root(self):
        self.make_suite(self._target_command())
        self.run_main()
        self.assertEqual((self.store / ".last" / "target.txt").read_text(),
                         str(self.repo))

    def test_project_root_mismatch(self):
        self.make_suite(write_results([]), project_root=self.tmp / "other")
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("black-qat: the suite for 'myrepo' belongs to "
                      "%s. Set \"project\" in black-qat.config.json to give this "
                      "repo its own suite." % (self.tmp / "other"), out)

    def test_bad_results(self):
        msg = ("black-qat: the suite did not produce readable results. "
               "The tester can inspect the raw log.")
        for command in ("true", pyc("import os;open(os.environ['BQ_RESULTS'],'w')"
                                    ".write('not json')"), "exit 1",
                        write_results([])):
            self.make_suite(command)
            code, out = self.run_main()
            self.assertEqual(code, 2, command)
            self.assertIn(msg, out)

    def test_stale_results_not_reused(self):
        self.make_suite(write_results([{"id": "BQ-001", "status": "pass"}]))
        self.run_main()
        self.make_suite("true")
        code, _ = self.run_main()
        self.assertEqual(code, 2)

    def test_register_last_run_updated(self):
        self.store.mkdir(parents=True)
        (self.store / "SCENARIOS.md").write_text(REGISTER)
        self.make_suite(write_results([
            {"id": "BQ-001", "status": "pass"},
            {"id": "BQ-002", "status": "fail"}]))
        self.run_main()
        text = (self.store / "SCENARIOS.md").read_text()
        import datetime
        today = datetime.date.today().isoformat()
        expected = (REGISTER
                    .replace("| never |", "| pass %s |" % today)
                    .replace("| pass 2020-01-01 |", "| fail %s |" % today))
        self.assertEqual(text, expected)

    def test_bin_is_executable_and_runs(self):
        binpath = LIB.parent / "bin" / "bq-run"
        self.assertTrue(os.stat(binpath).st_mode & stat.S_IXUSR)
        proc = subprocess.run([str(binpath)], cwd=str(self.repo), env=self.env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no suite", proc.stdout)


if __name__ == "__main__":
    unittest.main()
