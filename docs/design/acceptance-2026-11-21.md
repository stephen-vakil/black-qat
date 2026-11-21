# black-qat v0.1 end-to-end acceptance (2026-11-21)

Method: real headless sessions, `claude -p --plugin-dir <repo> --allowedTools "Read Write Edit Grep Glob Bash Agent Skill"` (Claude Code 2.1.323), run from a scratch git repo with `black-qat.config.json` = `{"project": "bq-acceptance-scratch"}`, `BQ_HOME` unset (store `~/.black-qat/bq-acceptance-scratch`), `BQ_OPEN_CMD=true`. No permission bypass. Other user plugins loaded too. For skill runs the prompt said "Invoke the skill /black-qat:X now; do not brainstorm" as a precaution (not confirmed to be necessary). Evidence is from `--output-format stream-json` transcripts. Home username replaced with `<user>`.

Result: all checks PASS. Notes at the bottom.

## Step 1: hook checks (store seeded by hand with a marker file, `run.json` and a trivial passing suite)

| Check | Result | Evidence |
|---|---|---|
| Root `Read` on store file | PASS | `PreToolUse:Read hook error: black-qat: the hidden test suite is off-limits to this agent. Humans can review it with /black-qat:open.` |
| Root `Grep` on store | PASS | same text, `PreToolUse:Grep ...` |
| Root `Glob` on store | PASS | same text, `PreToolUse:Glob ...` |
| Root `Bash cat $HOME/.black-qat/...` | PASS | same text, `PreToolUse:Bash ...` |
| Root `Bash ls ~/.black-qat` | PASS (denied) | same text |
| Root `bq-run` allowed | PASS | `1 passed, 0 failed` |
| Root `bq-open` allowed | PASS | `black-qat: opened 4 file(s) from /Users/<user>/.black-qat/bq-acceptance-scratch` |
| Control: `echo hello` | PASS | `hello` |
| General-purpose subagent: Read/Grep/Glob/Bash cat denied | PASS | the same four denial messages |
| General-purpose subagent `bq-run` denied | PASS | `PreToolUse:Bash hook error: black-qat: only the root session may run the black-qat runner` |
| Nested subagent (spawned by that subagent; Agent tool was available to it): same five calls | PASS | identical five denials, relayed verbatim in the subagent's report |
| Tester (`black-qat:black-qat-tester`) writes in store | PASS | `File created successfully at /Users/<user>/.black-qat/bq-acceptance-scratch/probe.txt` |
| Tester writes at spec path | PASS | `File created successfully at <scratch>/docs/black-qat/spec.md` |
| Tester write elsewhere (`<scratch>/src/x.txt`) denied | PASS | `PreToolUse:Write hook error: black-qat: the tester may only write in the suite store or the spec file`; file not created |

Tester probe was dispatched with `MODE: triage` header plus an explicit override instruction to make exactly three Write calls; it complied (and warned that W2 overwrote the spec, which was expected for the probe).

## Step 2: thin PRD (5-line notes-API PRD) via `/black-qat:spec`: PASS

Returned `SPEC_READY`, the spec path, and 16 `Needs decision` items (`[proposed]` e.g. `POST /notes` shape, 201 response, 400 error body, 280-char limit, base URL/port; `[inferred]` e.g. content type, "bad input" definition). Only 7 items were tagged `[stated: prd.md ...]` (HTTP, add, list, JSON, error on bad input, runs locally). The "How to run" item was `[proposed]` and the tester said tests cannot run until it is decided. No store directory was created (nothing tested).

## Step 3: full loop on a precise counter-API spec (stdlib `http.server`)

| Stage | Result | Evidence |
|---|---|---|
| `/black-qat:spec` on precise input | PASS | `SPEC_READY`; items overwhelmingly `[stated: CS line N ...]`; 3 `[inferred]` items asked for decision (405 content type, "compact JSON" spacing, 404/405 leave counter unchanged) |
| `/black-qat:scenarios` | PASS | `SCENARIOS_READY`, 24 scenarios, review hint, ambiguity list (HEAD/PUT/etc. on known paths, Allow header, query strings, ...). The three `[inferred]` items were not turned into tests. |
| `/black-qat:tests` (nothing implemented) | PASS | `TESTS_READY`, `0 passed, 24 failed`; failures clean: `python3 server.py` exits 2, no such file. Tester reported validating the suite against its own reference server (24/24) and 11 mutants, all in the store's gitignored `.last/`. |
| Implement `server.py` with deliberate bug (increment by 2); implementer did not read the store | done | commit in scratch repo |
| `/black-qat:verify` with bug | PASS | `7 passed, 17 failed: BQ-002, ...` then Implementation-bugs section (see below) |
| Fix, `/black-qat:verify` | PASS | `24 passed, 0 failed` |

Verify output with the bug: the Implementation bugs section had 17 items in the form Action/input, Observed, Required, Spec section (e.g. "Start a fresh server. Send one `POST /increment` with no body. Observed: ... `{"value":2}`. Required: `{"value": 1}` ... Spec section: Interface I1, I4; A3"). Grep of that section: 0 occurrences of `BQ-`, 0 of `def `, `assert`, `.py`, `run_suite`, `pytest`. The only IDs were in the "Run summary (for the caller)" section, as designed.

An unplanned real finding: the tester's suite found a second genuine bug in my server (HTTP `OPTIONS` to an unknown path returned the stdlib 501 HTML page rather than 404 JSON; spec I8 says any method). This was reported correctly as an implementation bug and fixed with the increment fix, so the first fix round was "fix both".

## Step 4: output shape: PASS

- `verify`: totals line with IDs for the caller, labeled sections, bug reports behavior-only (above). The green run returned just `24 passed, 0 failed`.
- `open` via `/black-qat:open` returned one line: `black-qat: opened 3 file(s) from /Users/<user>/.black-qat/bq-acceptance-scratch`; no file content printed.

## Step 5: cleanup

Scratch repo and `~/.black-qat/bq-acceptance-scratch` deleted; `~/.black-qat` removed (it was empty).

## Observations (not failures)

1. The `verify` session's summary prose includes details like "My command ran the suite twice by mistake" (the skill ran `bq-run` once in its Bash call per transcript with a fallback pattern `(command -v bq-run && bq-run) || .../bq-run`; the tester reported the suite ran twice). Harmless, but the root-visible prose is looser than the skill's "return sections only".
2. Bug reports describe test shape in behavior terms (e.g. "1000 increments over one persistent connection", "~8 KB body", "10 clients x 20 in parallel"). This is within the behavior-only rule but does reveal the kind of inputs the hold-out suite uses.
3. `bq-open` counted 4 files in the first run and 3 in the last (the latest-run summary file likely absent in the latter); not investigated.
4. Plugin hook matcher covers Read/Write/Edit/MultiEdit/NotebookEdit/Grep/Glob/Bash only, as documented; all probed denials worked.
