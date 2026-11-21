import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import guard  # noqa: E402

TESTER = "black-qat:black-qat-tester"


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(os.path.realpath(self._td.name))
        self.home = self.tmp / "home"
        self.store = self.home / ".black-qat"
        (self.store / "p").mkdir(parents=True)
        self.repo = self.tmp / "repo"
        (self.repo / ".git").mkdir(parents=True)
        (self.repo / "docs" / "black-qat").mkdir(parents=True)
        self.env = {"HOME": str(self.home)}

    def ev(self, tool, agent_type=None, agent_id=None, cwd=None, **tool_input):
        event = {"tool_name": tool, "tool_input": tool_input,
                 "cwd": str(cwd or self.repo)}
        if agent_type:
            event["agent_type"] = agent_type
        if agent_id:
            event["agent_id"] = agent_id
        return event

    def denied(self, event):
        self.assertIsNotNone(guard.decide(event, self.env), event)

    def allowed(self, event):
        self.assertIsNone(guard.decide(event, self.env), event)

    def store_reads(self, **who):
        h = str(self.home)
        link = self.tmp / "link"
        link.symlink_to(self.store)
        return [
            self.ev("Read", file_path=f"{h}/.black-qat/p/SCENARIOS.md", **who),
            self.ev("Grep", path="~/.black-qat", **who),
            self.ev("Glob", pattern="~/.black-qat/**", **who),
            self.ev("Bash", command="cat $HOME/.black-qat/p/t.py", **who),
            self.ev("Bash", command="ls ${HOME}/.black-qat", **who),
            self.ev("Read", file_path=f"{h}/.BLACK-QAT/p/x", **who),
            self.ev("Read", file_path=f"{link}/p/x", **who),
        ]

    def test_root_denied(self):
        for e in self.store_reads():
            self.denied(e)

    def test_subagent_denied(self):
        for e in self.store_reads(agent_id="a1", agent_type="general-purpose"):
            self.denied(e)
        for cmd in ("/x/black-qat/bin/bq-run --target .", "bq-open"):
            self.denied(self.ev("Bash", agent_id="a1",
                                agent_type="general-purpose", command=cmd))

    def test_custom_bq_home_and_relative_symlink(self):
        bq = self.tmp / "elsewhere"
        bq.mkdir()
        env = {"HOME": str(self.home), "BQ_HOME": str(bq)}
        e = self.ev("Read", file_path=str(bq / "p" / "x"))
        self.assertIsNotNone(guard.decide(e, env))
        (self.repo / "rel").symlink_to(self.store)
        e = self.ev("Read", file_path="rel/p/x")
        self.denied(e)

    def test_root_allowed(self):
        self.allowed(self.ev("Bash", command="/x/black-qat/bin/bq-run --target ."))
        self.allowed(self.ev("Read", file_path=str(self.repo / "src" / "app.py")))
        self.allowed(self.ev("Read", file_path=str(self.repo / "docs/black-qat/spec.md")))

    def test_tester(self):
        kw = dict(agent_type=TESTER, agent_id="t1")
        self.allowed(self.ev("Write", file_path=str(self.store / "p" / "t.py"), **kw))
        self.allowed(self.ev("Write", file_path=str(self.repo / "docs/black-qat/spec.md"), **kw))
        self.denied(self.ev("Write", file_path=str(self.repo / "src" / "app.py"), **kw))
        self.denied(self.ev("Edit", file_path="src/app.py", **kw))
        self.allowed(self.ev("Read", file_path=str(self.store / "p" / "x"), **kw))
        self.allowed(self.ev("Bash", command="cat ~/.black-qat/p/x; bq-run", **kw))

    def test_tester_cannot_escape_store_by_symlink_or_dotdot(self):
        kw = dict(agent_type=TESTER, agent_id="t1")
        (self.store / "p" / "out").symlink_to(self.repo / "src")
        self.denied(self.ev("Write", file_path=str(self.store / "p/out/a.py"), **kw))
        self.denied(self.ev("Write", file_path=str(self.store / "p/../../x"), **kw))
        self.denied(self.ev("Write", **kw))

    def test_tester_config_spec_path(self):
        (self.repo / "black-qat.config.json").write_text(
            json.dumps({"specPath": "specs/my.md"}))
        kw = dict(agent_type=TESTER, agent_id="t1")
        self.allowed(self.ev("Write", file_path=str(self.repo / "specs/my.md"), **kw))
        self.denied(self.ev("Write", file_path=str(self.repo / "docs/black-qat/spec.md"), **kw))

    def test_subagent_cannot_dispatch_tester(self):
        self.denied(self.ev("Agent", agent_type="general-purpose", agent_id="a1",
                            subagent_type=TESTER, prompt="x"))
        self.denied(self.ev("Task", agent_type="general-purpose", agent_id="a1",
                            subagent_type=TESTER, prompt="x"))

    def test_root_can_dispatch_tester(self):
        self.allowed(self.ev("Agent", subagent_type=TESTER, prompt="x"))

    def test_subagent_can_dispatch_other_agents(self):
        self.allowed(self.ev("Agent", agent_type="general-purpose", agent_id="a1",
                             subagent_type="Explore", prompt="x"))

    def test_grep_glob_argument_inspected(self):
        self.denied(self.ev("Grep", path="~", glob=".black-qat/**", pattern="x"))

    def test_bare_tester_type(self):
        self.allowed(self.ev("Write", agent_type="black-qat-tester", agent_id="t1",
                             file_path=str(self.store / "p" / "t.py")))
        self.denied(self.ev("Write", agent_type="black-qat-tester", agent_id="t1",
                            file_path=str(self.repo / "src" / "app.py")))

    def test_robustness(self):
        self.assertIsNone(guard.decide({}, self.env))
        self.assertIsNone(guard.decide({"tool_name": "Read", "tool_input": "str"}, self.env))
        self.allowed(self.ev("Read", file_path=123))
        self.allowed(self.ev("WebFetch", url="http://x/.black-qat"))

    def run_hook(self, stdin):
        return subprocess.run([sys.executable, str(ROOT / "hooks" / "guard.py")],
                              input=stdin, capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home)})

    def test_entry_point(self):
        r = self.run_hook("not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        e = self.ev("Read", file_path=str(self.store / "p" / "x"))
        r = self.run_hook(json.dumps(e))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        r = self.run_hook(json.dumps(self.ev("Read", file_path=str(self.repo / "a.py"))))
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
