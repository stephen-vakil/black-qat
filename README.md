# black-qat

A Claude Code plugin that does one job: turn whatever description of your system you have into **hidden, adversarial, black-box tests** of its promised behavior, and report results **without leaking the tests**.

Coding agents judged by tests they can see tend to game them (special-casing inputs, weakening assertions, hardcoding outputs). black-qat keeps a hold-out suite where the coding agent can't see it, and reports only totals plus behavior descriptions of what is wrong.

It works with any coding workflow (a plain main agent, superpowers, a human). You drive it from the root Claude Code session.

## Install

```
/plugin marketplace add stephen-vakil/black-qat
/plugin install black-qat@black-qat
```

Requirements: `python3` on PATH; macOS or Linux.

## Quick start

1. `/black-qat:spec` with a conversation, PRD, plan or existing spec. Review the contract spec it writes; decide the `[proposed]` and `[inferred]` items (run `spec` again with your decisions, or edit the spec file directly).
2. `/black-qat:scenarios` (this means "the spec is agreed"). Review the register with `/black-qat:open`; revise by running `scenarios` again with notes.
3. `/black-qat:tests` (this means "the register is approved"). Writes the hidden tests and runs them once.
4. Implement however you like.
5. `/black-qat:verify` whenever you want to know where things stand. Repeat until green.

## Commands

| Command | What it does | Returns |
|---|---|---|
| `/black-qat:spec` | Derives or revises the visible contract spec from your inputs | `SPEC_READY`, spec path, list of items needing a decision (or `BLOCKED: ...`) |
| `/black-qat:scenarios` | Writes the plain-English scenario register (no test code), plus a gaps list | `SCENARIOS_READY`, count, review hint, new ambiguities (or `BLOCKED: ...`) |
| `/black-qat:tests` | Writes the hidden tests and runs them once | `TESTS_READY` with pass/fail/skip counts, or `TESTS_BLOCKED` with the reason |
| `/black-qat:verify` | Runs the suite and reports | Totals line (`N passed, M failed: IDs`, plus `; K skipped: IDs (reason)` if any), then: implementation bugs, spec ambiguities, test defects fixed, couldn't run |
| `/black-qat:open` | Opens the review files in your viewer (human use) | One line; prints no content |

The runner (`bq-run`) prints one line and exits 0 (all pass), 1 (failures), 2 (error, e.g. no suite yet) or 3 (no failures, but some scenarios skipped). Only the "Implementation bugs" section is meant to be forwarded to whoever writes the code; the other sections are for you.

## Pass, fail, skip

Each scenario ends as one of:

- **pass**: the promised behavior was observed.
- **fail**: it wasn't, including when the system errors, crashes or can't be reached as the spec describes.
- **skip**: it couldn't run because required environment is missing (an env var, credential or external service that the spec's How to run/reach section lists). The reason names what's missing, e.g. `needs ANTHROPIC_API_KEY`.

A skip is never green: nothing was checked. It is never triaged or forwarded to implementers, since they can't fix your environment. A scenario may skip only for a precondition the spec lists, checked before the system is touched, so a broken product can't hide behind a skip.

## Spec tags and gaps

Every item in the spec is tagged:

- `[stated: <source>]`: traceable to your input, or confirmed by you. **Only these get tests.**
- `[proposed]`: a design decision your input doesn't make (error body shape, flag names). Returned to you as "needs decision".
- `[inferred]`: the tester's reading of something vague. Not tested until confirmed.

Confirmed items become `[stated: confirmed ...]`. Anything the contract doesn't define goes to `GAPS.md` for a human; it never becomes a failing test. A thin PRD gives a short contract and a long open-items list, on purpose.

## Where things live

- Spec (visible, in your repo): `docs/black-qat/spec.md`. A conversation given to `spec` is saved under `docs/black-qat/inputs/`.
- Hidden suite (a git repo of its own, outside your project): `~/.black-qat/<project>/`, holding the tests, `SCENARIOS.md` (register with last-run status), `GAPS.md`, `CHANGELOG.md` (every test change after approval, with spec justification), and `.last/` run output.
- Optional `black-qat.config.json` at the repo root:

```json
{ "project": "my-project", "specPath": "docs/specs/contract.md" }
```

`project` overrides the store name (default: repo directory name). `/black-qat:spec` creates this file with the current name on first use; commit it, so a renamed folder or a fresh clone still finds the same suite. Every git worktree of a repo shares the main checkout's suite, spec and config; runs from a worktree test that worktree by default; `specPath` overrides the spec location (relative to the repo root). No other settings.

## Human review

Use `/black-qat:open` to open `SCENARIOS.md`, `GAPS.md`, `CHANGELOG.md` and the latest run summary in your default viewer (`open` on macOS, `xdg-open` on Linux). To use a specific app, set `BQ_OPEN_CMD` to its command-line launcher, e.g. `"env": { "BQ_OPEN_CMD": "code" }` in your Claude Code settings for VS Code. black-qat's skills tell agents to run it rather than read the store themselves.

## How it hides the tests

- The tests live in `~/.black-qat/<project>/`, outside the repo, so they are never committed with your code.
- A `PreToolUse` hook shipped with the plugin denies any other agent's Read, Grep, Glob, Write, Edit and Bash calls that reference the store, and restricts the tester's file-edit tools (Write/Edit/MultiEdit/NotebookEdit) to the store and the spec file; its Bash is restricted by instruction only.
- Only the root session may run `verify` or `open`; subagents are denied the runner (black-qat's own tester excepted). Only the root session may dispatch the tester.
- The runner prints one summary line. Raw output stays in the store for the tester's triage.
- The forwarded implementation-bug section is behavior-only: what was done, what was observed, what the spec requires. No test code, assertions, file names or IDs (the run summary line does list IDs).

## Guarantees and limits

Read these before relying on it.

- **Enforcement exists only inside Claude Code.** Other tools (Cursor, Codex, ...) get only "the tests live outside the repo".
- **Bash matching is heuristic.** The hook looks for the literal string `.black-qat` and the resolved store paths. Globs like `~/.black*` or building the path from variables are not caught. The threat model is a corner-cutting agent, not a deliberately adversarial one.
- **False positive:** because of that match, the root session can't grep for the literal string `.black-qat`.
- **The tester's read restriction is instruction-only.** It is told never to read your implementation source; the hook restricts its writes, not its reads.
- **Root-as-coder caveat.** If your main session both writes code and runs `verify`, it sees summaries and behavior reports across rounds. For the strongest isolation, write code in subagents or a separate session.
- **Only the root session can run `verify` and `open`** (black-qat's own tester excepted), and only the root can dispatch the tester.
- **The system under test sees test inputs.** It runs during the suite and receives the tests' inputs; if that code logs incoming requests or arguments somewhere the coding agent can read, the agent sees them. The hook cannot prevent this.
- The hook fails open: if it errors, the call is allowed.

### Optional sandbox hardening

A plugin can't enable sandbox read-deny itself (no documented way; not confirmed by an end-to-end test). You can add it to your own user or project settings:

```json
{ "sandbox": { "enabled": true, "filesystem": { "denyRead": ["~/.black-qat"] } } }
```

Scope: this applies only to sandboxed shell commands. The built-in Read tool is governed by permission rules instead (for example a `Read` deny rule), and plugin hooks run outside the sandbox. The guard hook remains the primary enforcement. See `docs/design/build-notes.md` (Q4).

## More

- Design: `docs/design/2026-11-21-black-qat-design.md`
- Platform findings: `docs/design/build-notes.md`
- License: MIT
