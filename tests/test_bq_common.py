import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import bq_common  # noqa: E402


class BqCommonTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(os.path.realpath(self._td.name))

    def test_find_root_walks_up_to_git(self):
        (self.tmp / "repo" / ".git").mkdir(parents=True)
        cwd = self.tmp / "repo" / "a" / "b"
        cwd.mkdir(parents=True)
        self.assertEqual(bq_common.find_root(str(cwd)), self.tmp / "repo")

    def test_find_root_no_git_falls_back_to_cwd(self):
        cwd = self.tmp / "x"
        cwd.mkdir()
        root = bq_common.find_root(str(cwd))
        self.assertEqual(root, cwd)
        self.assertEqual(bq_common.project_name(root), "x")
        self.assertEqual(bq_common.spec_path(root), cwd / "docs/black-qat/spec.md")

    def test_git_file_counts(self):
        (self.tmp / "wt").mkdir()
        (self.tmp / "wt" / ".git").write_text("gitdir: /elsewhere")
        sub = self.tmp / "wt" / "sub"
        sub.mkdir()
        self.assertEqual(bq_common.find_root(str(sub)), self.tmp / "wt")

    def test_config_overrides_project_and_spec(self):
        (self.tmp / "black-qat.config.json").write_text(
            json.dumps({"project": "api2", "specPath": "specs/s.md"}))
        self.assertEqual(bq_common.project_name(self.tmp), "api2")
        self.assertEqual(bq_common.spec_path(self.tmp), self.tmp / "specs/s.md")

    def test_invalid_config_ignored(self):
        (self.tmp / "black-qat.config.json").write_text("not json")
        self.assertEqual(bq_common.load_config(self.tmp), {})
        self.assertEqual(bq_common.project_name(self.tmp), self.tmp.name)
        self.assertEqual(bq_common.spec_path(self.tmp),
                         self.tmp / "docs/black-qat/spec.md")

    def test_store_home_env_override_and_default(self):
        self.assertEqual(bq_common.store_home({"BQ_HOME": "/x"}), Path("/x"))
        self.assertEqual(bq_common.store_home({"HOME": "/h"}), Path("/h/.black-qat"))


if __name__ == "__main__":
    unittest.main()
