# Skip status (v0.2.0) Implementation Plan

> **For agentic workers:** small change; executed inline with TDD, then one fresh whole-branch review.

**Goal:** A scenario that cannot run because something outside the product is missing (an env var, a credential, an external service) is reported as `skipped` with a plain reason, never as pass or fail.

**Why:** In a real run, an agentic feature's tests could not run because an API key was missing. Calling that "fail" sends a fixer chasing an environment problem; calling it "pass" hides that nothing was checked. Both hid reality.

**Spec:** this plan (agreed in conversation, 2026-11-22). Design context: `2026-11-21-black-qat-design.md`.

## Global Constraints

- Results entry: `{"id": "BQ-001", "status": "pass" | "fail" | "skip"}`; a `skip` entry must also carry `"reason"`, a non-empty string. Anything else → unreadable results (exit 2), as today.
- Exit codes: 0 all pass; 1 any fail (takes priority over skips); 3 no fails but at least one skip; 2 error.
- Summary line with no skips is byte-identical to v0.1 (`N passed, M failed[: IDs]`). With skips it appends `; K skipped: <IDs> (<reason>)[, <IDs> (<reason>)]`, IDs grouped by reason, groups in order of first ID.
- The runner normalises each reason before printing: whitespace collapsed to single spaces, `|` replaced with `/`, cut to 80 characters.
- Register `Last run` for a skip: `skip <date> (<reason>)`.
- Skips are legal only for preconditions the spec's "How to run/reach" section lists as required environment. The tester checks the precondition before touching the system; if the product itself errors, it is a fail.
- Skips never count as green and are never triaged or forwarded to implementers.

## Review Focus

1. A skip entry without a reason must not be accepted silently (exit 2).
2. Mixed fail + skip must exit 1, not 3, and list both.
3. All-skipped must exit 3, not 0 or 2.
4. A reason containing newlines or `|` must not break the one-line summary or the register table.

---

### Task 1: Runner (`lib/bq_run.py`, `tests/test_bq_run.py`)

- [ ] Tests: `test_skip_with_reason` (2 pass + 1 skip → exit 3, line `2 passed, 0 failed; 1 skipped: BQ-003 (needs ANTHROPIC_API_KEY)`); `test_fail_and_skip` (exit 1, `1 passed, 1 failed: BQ-002; 2 skipped: BQ-003, BQ-004 (needs X), BQ-005 (needs Y)`-style grouping); `test_all_skipped` (exit 3); `test_skip_without_reason_is_unreadable` (missing / empty / non-string reason → exit 2); `test_reason_normalised` (newline and `|` and >80 chars); register test extended with a skip row.
- [ ] Run → fail. Implement: `_load_results` returns `{id: (status, reason)}`; `_summary(results) -> str`; exit code per constraints; `_update_register` writes `skip <date> (<reason>)`.
- [ ] Run all → pass. Commit.

### Task 2: Tester agent, skills, umpf, README, version

- [ ] `agents/black-qat-tester.md`: run contract allows `skip` + reason; skip rule (spec-listed precondition only, checked before touching the system, product errors are fails); spec mode lists required environment under How to run/reach (tagged like any item); tests mode replaces "No skipped tests" with the skip rule and returns counts incl. skipped; register `Last run` wording.
- [ ] `skills/verify/SKILL.md`: exit 3 → return totals + **Couldn't run — for the human** section (reasons); exit 1 → triage only the failing IDs, and include the Couldn't run section if the line has skips.
- [ ] `skills/tests/SKILL.md`: counts line includes skipped.
- [ ] `~/.claude/skills/umpf/SKILL.md` (personal, not in this repo): Couldn't run → ask the user to supply what's missing and verify again, or accept the skips; doesn't use a fix round; never green with unaccepted skips; accepted skips listed in the final message.
- [ ] README: result statuses, exit code 3, the skip rule, and `BQ_OPEN_CMD` (undocumented today).
- [ ] Bump `plugin.json` and `marketplace.json` to 0.2.0. Commit.

## Out of scope — ask

- Fake-provider seams so agentic tests run without a real key.
- A config switch to treat skips as failures in CI.

## Deferred from the whole-branch review (not implemented)

- Skips are trusted: nothing checks a skip reason against the spec's required-environment list.
- Bare repos: skills' `git worktree list` first line is the bare repo, so `projectRoot` mismatches (exit 2).
- A config committed only on a worktree branch is ignored; spec step 0 run from a worktree writes the config into the main checkout.
- The handback marker is written in PreToolUse; if another layer then denies the handback, SubagentStop skips that agent's final check.
- The stop hook ignores `stop_hook_active`; Claude Code's built-in cap of 8 consecutive stop-hook continuations bounds the bounce loop.
- A skip reason containing `(`, `)` or `,` makes the summary line ambiguous to parse.
