import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB))

import bq_open  # noqa: E402


class BqOpenTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(os.path.realpath(self._td.name))
        self.repo = self.tmp / "myrepo"
        (self.repo / ".git").mkdir(parents=True)
        self.home = self.tmp / "home"
        self.store = self.home / "myrepo"
        self.log = self.tmp / "opened.log"
        opener = self.tmp / "opener.sh"
        opener.write_text('#!/bin/sh\necho "$1" >> "%s"\n' % self.log)
        opener.chmod(opener.stat().st_mode | stat.S_IXUSR)
        self.env = dict(os.environ, BQ_HOME=str(self.home),
                        BQ_OPEN_CMD=str(opener))

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bq_open.main([], self.env, str(self.repo))
        return code, out.getvalue()

    def test_opens_existing_files_only(self):
        self.store.mkdir(parents=True)
        (self.store / "SCENARIOS.md").write_text("s")
        (self.store / "GAPS.md").write_text("g")
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "black-qat: opened 2 file(s) from %s"
                         % self.store)
        self.assertEqual(self.log.read_text().split(),
                         [str(self.store / "SCENARIOS.md"),
                          str(self.store / "GAPS.md")])

    def test_prints_no_content(self):
        self.store.mkdir(parents=True)
        (self.store / "SCENARIOS.md").write_text("SECRET")
        code, out = self.run_main()
        self.assertNotIn("SECRET", out)

    def test_no_suite(self):
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("black-qat: no suite for project 'myrepo'. "
                      "Run /black-qat:scenarios and /black-qat:tests first.", out)

    def test_bin_is_executable_and_runs(self):
        binpath = LIB.parent / "bin" / "bq-open"
        self.assertTrue(os.stat(binpath).st_mode & stat.S_IXUSR)
        proc = subprocess.run([str(binpath)], cwd=str(self.repo), env=self.env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no suite", proc.stdout)


if __name__ == "__main__":
    unittest.main()
