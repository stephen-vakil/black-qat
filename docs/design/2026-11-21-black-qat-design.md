# black-qat — design

Date: 2026-11-21
Status: draft, awaiting approval (builder check done)
Supersedes: `~/Documents/Code/harness/docs/superpowers/specs/2026-11-21-blackbox-tdd-harness-design.md` (most of its mechanics carry over; its superpowers orchestration moves to a future orchestrator plugin)

## Intent and why

Coding agents judged by tests they can see tend to game them (special-casing inputs, weakening assertions, skipping tests, hardcoding outputs). The industry answer is a **hold-out set**: acceptance tests derived independently from the requirements, never visible to the implementer, used as the arbiter of "done".

**black-qat** is an installable Claude Code plugin that does one job: *turn whatever description of the system you have into hidden, adversarial, black-box tests of its promised behavior, and report results without leaking the tests.* It works with any coding workflow (superpowers, a plain main agent, a human), driven from the root session — by a person typing commands, the main agent, or an orchestrator skill.

It is the first member of a planned set of cooperating plugins (the "superband"):

| Member | Role | Status |
|---|---|---|
| orchestrator | sequences the others; talks to the human; runs as a root-session skill | later |
| superpowers | plans and implements, with its own internal tests | exists |
| **black-qat** | derives the contract; writes and runs hidden black-box tests | **this design** |
| HEATH | ledger and agreed-scope enforcement | deferred |

The human stays a person in this set — no agent acts as the human's proxy.

## Goals

1. Derive a **contract spec** from whatever input is given (conversation transcript, PRD, plan, existing spec), revise it on request, and return it to the caller.
2. Propose a human-readable **scenario register**; after approval, write hidden adversarial tests for it.
3. Run the hidden suite against a given checkout and return **summary-only results** plus **behavior-only failure reports**.
4. Let the human see everything (`open`) without the content entering any agent's context.
5. **Enforce** the hiding inside Claude Code with a hook shipped by the plugin itself — on automatically once installed; no dependence on the orchestrator behaving.
6. Usable standalone by hand; every hand-off is a file or a simple status. **Driven only from the root session** (human decision): by a person, the main agent, or an orchestrator that runs as a skill in the root session. Spawned agents can't drive it. A way to authorize named driver agents may be added later if a real need appears (YAGNI now).

## Non-goals

- Orchestration: round caps, sequencing planning/implementation, deciding who fixes what. That's the caller's (future orchestrator's) job.
- Writing a *project design* (architecture, internal choices). black-qat writes only the externally observable contract.
- CI integration now. The design keeps it possible (summary-only runner) but builds none.
- Hard enforcement outside Claude Code (Cursor, Codex, etc.). There, the only protection is that tests live outside the project; the README says so plainly.
- Language/framework-specific support. The tester picks tooling per project; it prefers testing through external interfaces (HTTP, CLI) and uses the public API surface for libraries.
- The `~/Documents/Code/CLAUDE.md` YAGNI additions from the earlier discussion — a separate, small local change, not part of this plugin.

## Anti-goals

- Test content leaking to the coding side — via failure output, the caller's context, CI logs, or git history.
- black-qat inventing requirements: failing code over behavior the input never promised (a backdoor for scope creep).
- black-qat silently making design decisions (endpoint shapes, error formats) when deriving a spec.
- The tester bending tests to match the implementation.

## Core concepts

### The contract spec (visible)

The *what*, from the outside: interface (endpoints/commands/signatures, inputs/outputs, error behavior), acceptance criteria, and how to run/reach the system. Never internals. It is **not secret** — both the planner/implementer and black-qat work from the same agreed spec, which removes most "we read it differently" failures.

Every item is tagged:
- **Stated** — quoted from or directly traceable to the input (with a source reference). Gets tests.
- **Proposed** — a design decision the input doesn't make (e.g. "error responses use `{error: string}`"). Returned to the caller as *needs decision*; never tested until accepted.
- **Inferred** — black-qat's reading of something vague. Never tested until confirmed.

Accepted/confirmed items become stated (noting who confirmed and when). Given a plan as input, black-qat keeps only externally visible behavior and says it did so. Given a thin PRD, the result is a short contract plus a long list of open items — honest, not padded.

The spec is written to a visible path in the project: `docs/black-qat/spec.md` by default, changeable only via the repo-root config file *(my call: no per-call override, so the hook can read the one allowed path from config)*.

### The suite (hidden)

- One git repo per project at **`~/.black-qat/<project>/`**, outside any project tree (so recursive searches from code folders never traverse it, and project git history never contains it).
- Contents: tests; run configuration (how to start/reach the system given a target checkout path); a runner emitting **machine-readable results** (scenario ID + pass/fail); raw output (for the tester's triage only); `SCENARIOS.md` register; `GAPS.md` spec-gaps report; `CHANGELOG.md` logging every test change after approval with its justification.
- Scenario IDs are **opaque** (`BQ-001`, …). Meaning lives only inside the suite.
- Only the tester performs git operations in the suite.

### Adversarial, within the contract

Attack stated behavior hard: boundaries of stated limits, every stated error case, inputs crafted to break stated rules, sequences and state transitions the contract implies. Anything the contract doesn't define ("what about a 10 MB payload?") goes in `GAPS.md` for a human — never a failing test. Consistent with strict YAGNI.

## Commands (skills)

All namespaced under the plugin. Each returns a short status the caller can branch on.

| Command | Input | Does | Returns |
|---|---|---|---|
| `spec` | input file path(s); optional revision notes (including decisions on proposed/inferred items) | Tester derives or revises the contract spec | `SPEC_READY` + spec path + list of proposed/inferred items needing decisions |
| `scenarios` | (agreed spec path) | Tester writes `SCENARIOS.md` (no test code yet) and run config | `SCENARIOS_READY` + count + hint to review via `open` + any new ambiguities |
| `tests` | (approved register) | Tester writes tests and runs them once against the current checkout. Failures must be clean (behavior absent/wrong, never test errors). Tests that already pass are fine — e.g. black-qat used on an existing system — and are reported, not blocking. Commits the suite | `TESTS_READY` + initial pass/fail counts, or `TESTS_BLOCKED` + reason |
| `verify` | optional target checkout path (default: caller's repo root) | Runs suite; on failures dispatches tester in triage mode | totals + failing IDs, and per failure one of: **implementation bug** (behavior-only report: action/input, observed, required, spec section — no test code, assertion text, file names, or IDs), **spec ambiguity** (for the human), **test defect** (tester fixed it, logged in `CHANGELOG.md`) |
| `open` | — | Opens the suite's `SCENARIOS.md`, `GAPS.md`, `CHANGELOG.md`, and latest results in the human's editor/file viewer | one line ("opened …"); prints no content |

Revising scenarios after review = `scenarios` again with notes.

**Approval** *(my call)*: invoking the next command is the approval — calling `scenarios` means the spec is agreed; calling `tests` means the register is approved. The skill records this in the artifact (`Agreed: <date>` header in the spec, `Approved: <date>` in the register). Decisions on proposed/inferred items arrive as revision notes to `spec`, or the human edits the visible spec directly; the tester re-reads the spec on every run, so direct edits are picked up and the tags re-validated. No separate approve command; no gating beyond this.

**Existing systems** *(my call)*: supported. Since the tester can't read the implementation to rule out vacuous tests, its instructions require every test to assert on concrete observable output, and it reviews already-passing tests for that before reporting. No mutation testing (YAGNI). The register is updated whenever tests change; `verify` updates its last-run column.

If the human asks an agent to show/summarize the hidden tests, the plugin's skills direct it to `open` instead.

## Components

Plugin repo layout (exact paths left to the builder, standard Claude Code plugin structure):

- **Plugin manifest** + a **marketplace manifest** in the same repo, so users install with `/plugin marketplace add <owner>/black-qat` then `/plugin install black-qat`.
- **Skills**: `spec`, `scenarios`, `tests`, `verify`, `open`.
- **Agent**: one `tester` agent with modes (spec, scenarios, tests, triage). Tools: Read, Write, Edit, Grep, Glob, Bash. **No Agent tool** (never delegates), no web.
- **Guard hook** (PreToolUse), shipped in the plugin's hooks config.
- **Scripts**: summary runner (used by `verify`), opener (used by `open`, cross-platform: macOS/Linux at minimum).
- **README**: what it guarantees, what it doesn't (non-Claude-Code tools), how to review as a human, the "code in subagents or a separate session for strongest isolation" note (below).

## Guard hook

Fires on Read, Write, Edit, MultiEdit, NotebookEdit, Grep, Glob, Bash. Identifies the caller by `agent_type` / `agent_id` in the hook input (root session has neither).

- **Any agent other than black-qat's tester** — including the root session and agents from any other plugin, at any nesting depth: deny any call whose path argument or Bash command references the suite store (`~/.black-qat`, `$HOME/.black-qat`, or the absolute path). Exception: Bash invoking black-qat's own runner/opener scripts is allowed **for the root session only**. Subagents (e.g. superpowers implementers) can't run the suite — otherwise they could probe the hidden tests by trial and error.
- **The tester**: Write/Edit allowed only in the suite store and at the spec path (default, or read from the repo-root config). *(My call: the tester's **read** restriction — "only the input documents, never implementation source" — is enforced by its instructions, not the hook. The hook has no reliable way to know a given run's input files, and the critical direction is coder-can't-see-tests, which the hook does enforce.)*
- Denials return a clear reason so agents don't hunt for workarounds.
- Known, accepted limitation: Bash path matching is heuristic. The threat model is a corner-cutting agent, not a deliberately adversarial one.

**Root-as-coder caveat:** if a user's main session both writes code and runs `verify`, that session sees summaries and behavior reports across rounds. Still no test code, but weaker isolation than coding in subagents or a separate session. Documented, not prevented.

To check during the build (unknown today): the plugin agent's exact `agent_type` string as seen by hooks (namespaced or not); whether a plugin can enable Claude Code's OS sandbox read-deny for the store or must document it as an opt-in hardening step.

## Project identity and configuration

- `<project>` defaults to the basename of the caller's git repo root. *(My call.)*
- An optional small config file at the repo root may override the project name and the spec output path. No other settings until a real need appears (no "may write specs" switch — the stated/proposed/inferred tagging replaces it).

## Typical flows

**With a future orchestrator (the superband):**
conversation/plan → `spec` → orchestrator (and human) review, request revisions → `spec` again → agreed → in parallel: `scenarios` and the planner's plan → one human checkpoint (plan + register via `open`) → in parallel: `tests` and implementation → `verify` → orchestrator routes bug reports to the implementer, ambiguities to the human, applies its own round cap → repeat `verify` → done.

**By hand:** a person runs the same commands in order and opens the register themselves.

## Left to the builder

- Hook language and path-matching code (must cover `~`, `$HOME`, and absolute forms).
- Results-file format, run-config schema, spec document template.
- Exact skill/agent prompt wording, following this design.
- Model choice for the tester (default: inherit).

## Verification (acceptance for black-qat itself)

In a scratch project with the plugin installed:
- Root session `Read`/`Grep`/`Glob`/`Bash cat` on the store → denied. Root running `verify`/`open` → allowed.
- A subagent, and a subagent it spawns, attempting the same reads or running the runner → denied.
- Tester can write in the store and at the spec path; denied writes elsewhere.
- `verify` output contains only totals, IDs, and behavior-only reports; `open` prints nothing but one line.
- `spec` on a thin PRD tags items correctly and returns proposed/inferred items rather than testing them.
- End-to-end on a tiny API spec: spec → scenarios → tests (fail cleanly) → a deliberately buggy implementation → `verify` returns a correct behavior-only bug report → fix → green.
