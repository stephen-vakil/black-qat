# black-qat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build black-qat, an installable Claude Code plugin that derives a contract spec, writes hidden adversarial black-box tests, runs them with summary-only output, and enforces the hiding with a plugin-shipped PreToolUse hook.

**Architecture:** Plugin repo = manifest + marketplace manifest, one tester agent, five skills (`spec`, `scenarios`, `tests`, `verify`, `open`), a Python guard hook, and two Python scripts (`bq-run`, `bq-open`). All logic lives in `lib/` modules with thin entry points so it is unit-testable. Skills and the agent are Markdown prompts verified end-to-end in the final task.

**Tech Stack:** Python 3 (stdlib only — no third-party deps), `unittest`, Claude Code plugin format (Claude Code 2.1.x: `claude plugin validate`, `claude --plugin-dir`).

**Spec:** `docs/design/2026-11-21-black-qat-design.md`

## Global Constraints

- Python 3 stdlib only; every script runs with `python3`. Tests run with `python3 -m unittest discover -s tests -v`.
- Suite store: `~/.black-qat/<project>/`; overridable via env `BQ_HOME` (used by tests).
- Default spec path: `docs/black-qat/spec.md` relative to the project root; only override is `specPath` in `black-qat.config.json` at the project root. Config may also set `project`. No other config keys.
- `<project>` = config `project`, else basename of the git repo root (root = nearest ancestor containing `.git`, else cwd).
- Scenario IDs: `BQ-` + 3 digits (`BQ-001`).
- Tester agent name: `black-qat-tester`. The guard accepts `agent_type` values `black-qat-tester` and `black-qat:black-qat-tester`.
- Only the root session (hook input has no `agent_id`) may run `bq-run`/`bq-open`.
- Outputs to agents never contain test code, assertion text, or test file names. `bq-run` prints only totals and failing IDs; `bq-open` prints one line.
- Supported OS: macOS and Linux.
- Do not modify anything outside this repo except via `claude --plugin-dir` sessions and scratch directories during verification.

## Review Focus

1. **Path spelling variants** — `~/.black-qat`, `$HOME/.black-qat`, `${HOME}/.black-qat`, absolute path, mixed case (macOS is case-insensitive), symlinked/`/private` prefixed paths: all must be recognized as the store. Tests in Task 3.
2. **Malformed or unexpected hook input** — invalid JSON, missing `tool_input`, unknown tool names, non-string fields: guard must allow (exit 0, no output) and never crash. Tests in Task 3.
3. **Two repos with the same basename** sharing one store — `bq-run` must refuse with a message naming the fix (set `project` in config) rather than running another project's suite. Test in Task 4.
4. **Suite that can't run or produces bad results** (missing `run.json`, command exits non-zero without results, invalid results JSON) — `bq-run` prints a one-line error with no raw output, exits 2. Tests in Task 4.
5. **Running outside a git repo** — root falls back to cwd; project name and spec path still resolve. Test in Task 2.

---

### Task 1: Plugin scaffold + platform findings

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.gitignore`, `docs/design/build-notes.md`
- Create (temporary, deleted at end of task): `agents/black-qat-tester.md` stub, `hooks/hooks.json` + `hooks/log_event.py` logging stub, `skills/probe/SKILL.md`

**Interfaces:**
- Produces: `docs/design/build-notes.md` answering exactly these questions, each with the evidence (log excerpt or command output):
  1. The exact `agent_type` string the hook sees for the plugin agent `black-qat-tester` (and whether `agent_id` is present for it and absent for root).
  2. The name under which the plugin's skills are invoked (e.g. `/black-qat:verify`) and the `subagent_type` string used to dispatch the plugin agent.
  3. How a skill should reference a plugin script: is `${CLAUDE_PLUGIN_ROOT}` substituted inside SKILL.md content, and/or is a plugin `bin/` directory on the Bash tool's PATH?
  4. Whether a plugin can enable Claude Code's sandbox filesystem read-deny for a path (search the official docs on plugins + sandboxing; cite URL). If not, the README documents it as optional user hardening (with the settings snippet if one exists).

- [ ] **Step 1:** Write `plugin.json` (`name: "black-qat"`, `version: "0.1.0"`, description from the spec intent, `license: "MIT"`, `author.name: "black-qat contributors"` — owner fills real details at publish time) and `marketplace.json` (`name: "black-qat"`, `owner.name: "black-qat contributors"`, one plugin entry with `source: "./"`). Model the shape on `~/.claude/plugins/marketplaces/posthog/.claude-plugin/marketplace.json`.
- [ ] **Step 2:** Run `claude plugin validate .` — Expected: valid.
- [ ] **Step 3:** Add the temporary stubs: a PreToolUse hook (matcher `Bash|Read`) running `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/log_event.py"` that appends stdin JSON to `$TMPDIR/bq-probe.log`; a minimal `black-qat-tester` agent (tools: Bash); a `probe` skill whose body runs `echo ${CLAUDE_PLUGIN_ROOT}` and `which bq-probe` (add `bin/bq-probe` printing `ok`).
- [ ] **Step 4:** From a scratch dir, run `claude -p --plugin-dir <repo> "invoke the black-qat probe skill, then dispatch the black-qat-tester agent to run 'echo hi'"`, then inspect the log. Answer questions 1–3 in `build-notes.md` with excerpts.
- [ ] **Step 5:** Research question 4 in the docs; record answer + URL.
- [ ] **Step 6:** Delete all temporary stubs; re-run `claude plugin validate .`.
- [ ] **Step 7:** Commit: `chore: plugin scaffold and platform findings`.

---

### Task 2: Shared resolution module

**Files:**
- Create: `lib/bq_common.py`, `tests/test_bq_common.py`, `tests/__init__.py`

**Interfaces:**
- Produces (all in `lib/bq_common.py`):
  - `TESTER_AGENT_TYPES: frozenset[str]` = `{"black-qat-tester", "black-qat:black-qat-tester"}`
  - `find_root(cwd: str) -> Path` — nearest ancestor (inclusive) containing `.git` (dir or file); else `Path(cwd)`.
  - `load_config(root: Path) -> dict` — parsed `root/"black-qat.config.json"`; `{}` if absent or invalid JSON or not an object.
  - `project_name(root: Path) -> str` — config `project` if non-empty string, else `root.name`.
  - `store_home(env: Mapping[str, str]) -> Path` — `Path(env["BQ_HOME"])` if set, else `Path(env.get("HOME", "~")).expanduser() / ".black-qat"`.
  - `store_dir(root: Path, env) -> Path` — `store_home(env) / project_name(root)`.
  - `spec_path(root: Path) -> Path` — `root / config["specPath"]` if non-empty string, else `root / "docs/black-qat/spec.md"`.
- Tests import modules via `sys.path.insert(0, <repo>/lib)` at the top of each test file.

- [ ] **Step 1: Write failing tests** in `tests/test_bq_common.py` (use `tempfile.TemporaryDirectory`):
  - `test_find_root_walks_up_to_git`: `tmp/repo/.git/` + cwd `tmp/repo/a/b` → `tmp/repo`.
  - `test_find_root_no_git_falls_back_to_cwd` (Review Focus 5): cwd `tmp/x` → `tmp/x`; and `project_name` → `"x"`; `spec_path` → `tmp/x/docs/black-qat/spec.md`.
  - `test_git_file_counts` (worktrees use a `.git` file): `tmp/wt/.git` as a file → root `tmp/wt`.
  - `test_config_overrides_project_and_spec`: config `{"project": "api2", "specPath": "specs/s.md"}` → `"api2"`, `root/"specs/s.md"`.
  - `test_invalid_config_ignored`: config text `not json` → `{}`, default name and spec path.
  - `test_store_home_env_override_and_default`: `{"BQ_HOME": "/x"}` → `/x`; `{"HOME": "/h"}` → `/h/.black-qat`.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_bq_common -v` — Expected: FAIL (ModuleNotFoundError).
- [ ] **Step 3:** Implement the functions above.
- [ ] **Step 4:** Run tests — Expected: all PASS.
- [ ] **Step 5:** Commit: `feat: project/store/spec resolution`.

---

### Task 3: Guard hook

**Files:**
- Create: `lib/guard.py`, `hooks/guard.py` (entry point), `hooks/hooks.json`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `bq_common.find_root, store_home, spec_path, TESTER_AGENT_TYPES`.
- Produces:
  - `decide(event: dict, env: Mapping[str, str]) -> str | None` — deny reason, or `None` to allow.
  - `hooks/guard.py`: reads stdin JSON; on parse error exit 0 silently; if `decide` returns a reason, print `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": <reason>}}` and exit 0; else exit 0 with no output. Inserts `../lib` on `sys.path`.
  - `hooks/hooks.json`: PreToolUse, matcher `Read|Write|Edit|MultiEdit|NotebookEdit|Grep|Glob|Bash`, command `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"`.

**Rules `decide` implements** (event fields: `tool_name`, `tool_input`, `agent_type`, `agent_id`, `cwd`):
- Candidate strings = the string values of `tool_input` keys `file_path`, `notebook_path`, `path`, `pattern`, `command` (ignore non-strings/missing).
- *References the store* = lowercased candidate contains `.black-qat`, or contains the lowercased `store_home(env)` string or its `os.path.realpath`.
- If `agent_type ∈ TESTER_AGENT_TYPES`: for `Write|Edit|MultiEdit|NotebookEdit`, resolve the target (`file_path`/`notebook_path`, relative → joined to `cwd`) with `realpath`; allow if under `realpath(store_home)` or equal to `realpath(spec_path(find_root(cwd)))`; else deny `"black-qat: the tester may only write in the suite store or the spec file"`. Everything else allowed.
- Else, if any candidate references the store → deny `"black-qat: the hidden test suite is off-limits to this agent. Humans can review it with /black-qat:open."`
- Else, if `agent_id` is truthy, `tool_name == "Bash"`, and `command` matches `\bbq-(run|open)\b` → deny `"black-qat: only the root session may run the black-qat runner"`.
- Else allow. Any exception inside `decide` → allow (fail open; Review Focus 2).

- [ ] **Step 1: Write failing tests** (`env = {"HOME": tmp_home}`; build events with a helper `ev(tool, agent_type=None, agent_id=None, cwd=..., **tool_input)`):
  - Root denied: `Read file_path=<home>/.black-qat/p/SCENARIOS.md`; `Grep path=~/.black-qat`; `Glob pattern=~/.black-qat/**`; `Bash command="cat $HOME/.black-qat/p/t.py"`; `Bash command="ls ${HOME}/.black-qat"`; `Read file_path=<home>/.BLACK-QAT/p/x` (Review Focus 1); `Read` via a symlink to the store (create `tmp/link -> <home>/.black-qat`, read `tmp/link/p/x` — only realpath catches this; assert denied by resolving candidates that are paths with `realpath` too).
  - Subagent (`agent_id="a1", agent_type="general-purpose"`) denied the same reads, and denied `Bash command="/x/black-qat/bin/bq-run --target ."` and `"bq-open"`.
  - Root allowed: `Bash command="/x/black-qat/bin/bq-run --target ."`; `Read file_path=<repo>/src/app.py`; `Read file_path=<repo>/docs/black-qat/spec.md`.
  - Tester (`agent_type="black-qat:black-qat-tester", agent_id="t1"`): allowed `Write` under store; allowed `Write` to `<repo>/docs/black-qat/spec.md` (cwd = repo with `.git`); allowed `Write` to config-overridden spec path; denied `Write <repo>/src/app.py`; allowed `Read` under store; allowed `Bash` anything.
  - Bare `agent_type="black-qat-tester"` treated as tester too.
  - Robustness: `decide({}, env)` → None; `tool_input` = `"str"` → None; `file_path=123` → None; unknown `tool_name="WebFetch"` with `url` containing `.black-qat` → None (only listed keys inspected).
  - Entry point: subprocess `python3 hooks/guard.py` with stdin `not json` → exit 0, empty stdout; with a root store Read event → stdout JSON has `permissionDecision == "deny"`.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_guard -v` — Expected: FAIL.
- [ ] **Step 3:** Implement `decide`, the entry point, and `hooks.json`. For symlinks: for candidates from path keys (`file_path`, `notebook_path`, `path`), also check `realpath(expanduser(candidate joined to cwd))`.
- [ ] **Step 4:** Run tests — Expected: all PASS. Run `claude plugin validate .` — Expected: valid.
- [ ] **Step 5:** Commit: `feat: guard hook hides the suite store`.

---

### Task 4: Summary runner `bq-run`

**Files:**
- Create: `lib/bq_run.py`, `bin/bq-run` (executable, `#!/usr/bin/env python3`, inserts `../lib`, calls `sys.exit(bq_run.main(sys.argv[1:], os.environ, os.getcwd()))`), `tests/test_bq_run.py`

**Interfaces:**
- Consumes: `bq_common.find_root, store_dir, project_name`.
- Produces:
  - `main(argv: list[str], env: Mapping[str, str], cwd: str) -> int` — exit 0 all pass, 1 any fail, 2 error.
  - **Suite run contract** (the tester's Task 6 instructions depend on it): `<store>/run.json` = `{"projectRoot": "<abs path>", "command": "<shell command>"}`. `bq-run` executes `command` with `shell=True`, `cwd=<store>`, env plus `BQ_TARGET=<target abs path>` and `BQ_RESULTS=<store>/.last/results.json`; stdout+stderr go to `<store>/.last/raw.log`. The command must write `BQ_RESULTS` as a JSON list of `{"id": "BQ-001", "status": "pass" | "fail"}`.
  - Writes `<store>/.last/summary.txt` = the printed line + ISO timestamp.
  - **Register format** (shared with Task 6): `SCENARIOS.md` contains a Markdown table with header `| ID | Title | What it checks | Spec ref | Last run |`; `bq-run` rewrites the `Last run` cell of each `| BQ-…` row to `pass YYYY-MM-DD` / `fail YYYY-MM-DD`, leaving all other text unchanged.

**Messages (exact):**
- No suite: `black-qat: no suite for project '<name>'. Run /black-qat:scenarios and /black-qat:tests first.` → 2
- Store/root mismatch (Review Focus 3): `black-qat: the suite for '<name>' belongs to <projectRoot>. Set "project" in black-qat.config.json to give this repo its own suite.` → 2
- Bad results (Review Focus 4): `black-qat: the suite did not produce readable results. The tester can inspect the raw log.` → 2
- Success: `<p> passed, <f> failed` plus `: BQ-004, BQ-009` (sorted) when f > 0.

- [ ] **Step 1: Write failing tests** (`BQ_HOME` = tmp store home; repo = tmp dir with `.git`; suite `command` = small `python3 -c` scripts writing results):
  - `test_no_suite` → message + 2.
  - `test_all_pass` → `"3 passed, 0 failed"`, 0; `summary.txt` exists.
  - `test_failures_listed` → `"1 passed, 2 failed: BQ-002, BQ-003"`, 1.
  - `test_output_hides_raw`: command prints `SECRET-ASSERTION` to stdout/stderr → captured stdout of `main` doesn't contain it; `raw.log` does.
  - `test_target_passed_through`: command writes `$BQ_TARGET` into results-adjacent file; `--target /some/path` → that value; default target = repo root.
  - `test_project_root_mismatch` → mismatch message, 2.
  - `test_bad_results`: no results file / invalid JSON / command exits 1 with no file → bad-results message, 2.
  - `test_register_last_run_updated`: register with 2 rows + surrounding prose → only `Last run` cells change.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_bq_run -v` — Expected: FAIL.
- [ ] **Step 3:** Implement `main` (argparse with `--target`).
- [ ] **Step 4:** Run tests — Expected: all PASS.
- [ ] **Step 5:** Commit: `feat: summary-only suite runner`.

---

### Task 5: Opener `bq-open`

**Files:**
- Create: `lib/bq_open.py`, `bin/bq-open` (same entry pattern as `bin/bq-run`), `tests/test_bq_open.py`

**Interfaces:**
- Consumes: `bq_common.find_root, store_dir, project_name`.
- Produces: `main(argv, env, cwd) -> int`. Opens each existing file of `SCENARIOS.md`, `GAPS.md`, `CHANGELOG.md`, `.last/summary.txt` in the store using the command from env `BQ_OPEN_CMD` if set, else `open` on macOS / `xdg-open` on Linux (one invocation per file, `subprocess.run([cmd, path])`). Prints exactly `black-qat: opened <n> file(s) from <store>` → 0. No store → the Task 4 no-suite message → 2.

- [ ] **Step 1: Write failing tests:** `BQ_OPEN_CMD` = a tmp script appending its arg to a log. `test_opens_existing_files_only` (store with SCENARIOS.md + GAPS.md → log has those 2 paths, output line says 2); `test_prints_no_content` (SCENARIOS.md contains `SECRET` → stdout lacks it); `test_no_suite` → 2.
- [ ] **Step 2:** Run — Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run full suite `python3 -m unittest discover -s tests -v` — Expected: all PASS.
- [ ] **Step 5:** Commit: `feat: human opener for the hidden suite`.

---

### Task 6: Tester agent

**Files:**
- Create: `agents/black-qat-tester.md`

**Interfaces:**
- Consumes: run contract and register format (Task 4), spec path rules (Task 2), findings (Task 1).
- Produces: agent `black-qat-tester`, frontmatter `tools: Read, Write, Edit, Grep, Glob, Bash` (no Agent, no web tools). The prompt's mode is selected by a first line in the dispatch prompt: `MODE: spec | scenarios | tests | triage`, plus `PROJECT_ROOT:`, `STORE:`, `SPEC:` lines supplied by the skill.

**The prompt must specify** (wording is the implementer's, content is fixed by the spec):
- Universal rules: read only the input documents, the spec, and the store — never implementation source, even via Bash; never put test code, assertion text, test file names, or scenario IDs in anything returned for implementers; test only **stated** items; adversarial within the contract (boundaries of stated limits, every stated error case, inputs crafted to break stated rules, implied sequences/state); anything the contract doesn't define → `GAPS.md`, never a failing test; never change a test to match the implementation.
- **spec mode:** inputs = file paths + optional revision notes. Write/revise the spec at `SPEC` with sections Interface, Acceptance criteria, How to run/reach; every item tagged `[stated: <source ref>]`, `[proposed]`, or `[inferred]`. From a plan, keep only externally visible behavior and say so at the top. Apply revision notes / human edits; accepted items become `[stated: confirmed <who> <date>]`. Return `SPEC_READY`, the spec path, and the list of proposed/inferred items.
- **scenarios mode:** add `Agreed: <date>` header to the spec. Create store (`git init` if absent). Write `SCENARIOS.md` (register format from Task 4, `Last run` = `—`), `GAPS.md`, and `run.json` (`projectRoot` = `PROJECT_ROOT`). No test code. Return `SCENARIOS_READY`, count, "review with /black-qat:open", new ambiguities.
- **tests mode:** add `Approved: <date>` to the register. Write tests honoring the run contract (results JSON per scenario ID; target via `BQ_TARGET`), preferring external interfaces (HTTP/CLI), public API for libraries. Every test asserts on concrete observable output. Run once via the suite command; failures must be clean (behavior absent/wrong, not test errors); already-passing tests are allowed after checking they assert something concrete. Commit the store. Return `TESTS_READY` + initial pass/fail counts, or `TESTS_BLOCKED` + reason.
- **triage mode:** given failing IDs, read `.last/raw.log` and results; classify each: implementation bug → report `{action/input, observed, required, spec section}` with no IDs/test code; spec ambiguity → explanation for the human; test defect (test contradicts spec) → fix, log in `CHANGELOG.md` with spec citation, commit. Keep `SCENARIOS.md` current on any test change. Return the classified list.

- [ ] **Step 1:** Write the agent file.
- [ ] **Step 2:** Run `claude plugin validate .` — Expected: valid; agent listed by `claude plugin details <repo path or name>`.
- [ ] **Step 3:** Commit: `feat: black-qat tester agent`.

---

### Task 7: Skills

**Files:**
- Create: `skills/spec/SKILL.md`, `skills/scenarios/SKILL.md`, `skills/tests/SKILL.md`, `skills/verify/SKILL.md`, `skills/open/SKILL.md`

**Interfaces:**
- Consumes: invocation names, `subagent_type` string, and script-reference method from `build-notes.md` (Task 1); tester modes (Task 6); scripts (Tasks 4–5).
- Produces: each skill, run in the root session, (1) computes `PROJECT_ROOT` (git root of cwd), `STORE` (`~/.black-qat/<project>` per Task 2 rules — the skill states the path; it never reads it), `SPEC`; (2) acts; (3) returns the status line to the caller. Every skill includes: "Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open." Descriptions start with "Use when…" and name the trigger (e.g. spec: "Use when you have a conversation, PRD, plan or spec and want black-qat to derive or revise the contract spec").

| Skill | Action |
|---|---|
| spec | dispatch tester `MODE: spec` with the input paths (a conversation → the skill first writes it to a file under the project's `docs/black-qat/inputs/`) and revision notes; return its result |
| scenarios | dispatch tester `MODE: scenarios`; return result |
| tests | dispatch tester `MODE: tests`; return result |
| verify | run `bq-run [--target <path>]`; on exit 1 dispatch tester `MODE: triage` with the failing IDs; return totals + triage list; on exit 2 return the error line |
| open | run `bq-open`; return its line |

- [ ] **Step 1:** Write the five skills.
- [ ] **Step 2:** Run `claude plugin validate .` — Expected: valid; five skills listed by `claude plugin details`.
- [ ] **Step 3:** Commit: `feat: black-qat skills`.

---

### Task 8: README

**Files:**
- Create: `README.md`, `LICENSE` (MIT, holder "black-qat contributors")

- [ ] **Step 1:** Write README covering: what it does (one job); install (`/plugin marketplace add <owner>/black-qat`, `/plugin install black-qat@black-qat`); requirements (python3, macOS/Linux); the five commands and statuses; the stated/proposed/inferred tags and gaps policy; where things live; human review via `/black-qat:open`; **guarantees and limits** (hook enforcement only inside Claude Code; heuristic Bash matching; tester read restriction is instruction-only; root-as-coder caveat: "for strongest isolation, write code in subagents or a separate session"); optional sandbox hardening per `build-notes.md` Q4; config file keys (`project`, `specPath`).
- [ ] **Step 2:** Commit: `docs: README`.

---

### Task 9: End-to-end acceptance

**Files:**
- Create: `docs/design/acceptance-2026-11-21.md` (results log)

Run in a scratch git repo (scratchpad dir) with `claude -p --plugin-dir <repo>` sessions and `BQ_HOME` unset (real `~/.black-qat`, using a project name `bq-acceptance-scratch`; delete that store dir at the end). Record each check with pass/fail and evidence.

- [ ] **Step 1: Hook checks (spec Verification bullets 1–4):** root `Read`/`Grep`/`Glob`/`Bash cat` on the store → denied; root `bq-run`/`bq-open` → allowed; a subagent and a nested subagent attempting the same → denied; tester writes in store and spec path OK, elsewhere denied.
- [ ] **Step 2: Thin PRD:** `/black-qat:spec` on a 5-line PRD for a two-endpoint HTTP API → returns proposed/inferred items, tests nothing.
- [ ] **Step 3: Full loop** on a precise spec for a tiny two-endpoint API (Python stdlib `http.server`): spec → scenarios → tests (all fail cleanly, nothing implemented) → implement with one deliberate bug → `/black-qat:verify` returns a behavior-only bug report (no IDs/test code in the report text) → fix → green.
- [ ] **Step 4:** Confirm `verify` output has only totals/IDs/reports and `open` prints one line.
- [ ] **Step 5:** Clean up scratch repo and `~/.black-qat/bq-acceptance-scratch`; commit the results log: `test: end-to-end acceptance`.
