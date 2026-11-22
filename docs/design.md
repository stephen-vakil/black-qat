# black-qat — design

Why black-qat works the way it does. For how to use it, see the [README](../README.md).

## Intent

Coding agents judged by tests they can see tend to game them: special-casing inputs, weakening assertions, skipping tests, hardcoding outputs. The standard answer is a **hold-out set**: acceptance tests derived independently from the requirements, never shown to the implementer, used as the arbiter of "done".

black-qat does one job: *turn whatever description of the system you have into hidden, adversarial, black-box tests of its promised behavior, and report results without leaking the tests.* It works with any coding workflow (an agent framework, a plain main agent, a human) and is driven from the root session, by a person or by an orchestrating skill.

## Goals

1. Derive a **contract spec** from whatever input is given (conversation, PRD, plan, existing spec), and revise it on request.
2. Propose a human-readable **scenario register**; after approval, write hidden adversarial tests for it.
3. Run the hidden suite against a checkout and return **summary-only results** plus **behavior-only failure reports**.
4. Let the human see everything (`open`) without the content entering any agent's context.
5. **Enforce** the hiding inside Claude Code with hooks shipped by the plugin, active as soon as it is installed, so it doesn't depend on an orchestrator behaving.
6. Usable by hand; every hand-off is a file or a short status. Driven only from the root session; spawned agents can't drive it.

## Non-goals

- Orchestration: round caps, sequencing planning and implementation, deciding who fixes what. That's the caller's job.
- A project design (architecture, internal choices). black-qat writes only the externally observable contract.
- CI integration. The summary-only runner keeps it possible; none is built.
- Enforcement outside Claude Code. Elsewhere the only protection is that the tests live outside the project.
- Language- or framework-specific support. The tester picks tooling per project and prefers external interfaces (HTTP, CLI); for libraries it uses the public API.

## Anti-goals

- Test content leaking to the coding side, through failure output, the caller's context, CI logs or git history.
- black-qat inventing requirements: failing code over behavior the input never promised.
- black-qat silently making design decisions (endpoint shapes, error formats) when deriving a spec.
- The tester bending tests to match the implementation.

## Core concepts

### The contract spec (visible)

The *what*, from outside: interface (endpoints, commands, signatures, inputs, outputs, errors), acceptance criteria, and how to run or reach the system, including any required environment (env vars, credentials, external services; names only). Never internals. It is not secret: the implementer and black-qat work from the same agreed spec, which removes most "we read it differently" failures.

Every item is tagged:

- **stated**: traceable to the input, or confirmed by the user. Only these get tests.
- **proposed**: a design decision the input doesn't make. Returned as *needs decision*.
- **inferred**: black-qat's reading of something vague. Not tested until confirmed.

A thin PRD gives a short contract and a long list of open items, on purpose. The spec lives at one visible path (`docs/black-qat/spec.md`, or `specPath` in the config), so the hook knows the single file the tester may write outside the store.

### The suite (hidden)

- One git repo per project at `~/.black-qat/<project>/`, outside any project tree, so searches from the code never traverse it and project history never contains it.
- Holds the tests, `run.json` (how to run them), `SCENARIOS.md` (the register), `GAPS.md` (what the contract leaves open), `CHANGELOG.md` (every test change after approval, with its spec justification) and `.last/` (latest raw output and results, for triage only).
- Scenario IDs are opaque (`BQ-001`). Their meaning lives only inside the suite.

### Adversarial, within the contract

Attack stated behavior hard: boundaries of stated limits, every stated error case, inputs crafted to break stated rules, sequences and state transitions the contract implies. Anything the contract doesn't define goes to `GAPS.md` for a human and never becomes a failing test.

### Pass, fail, skip

Each scenario ends as **pass**, **fail**, or **skip**. Calling an unrunnable test "fail" sends a fixer chasing an environment problem; calling it "pass" hides that nothing was checked. So a scenario that can't run because spec-listed required environment is missing reports `skip` with a reason that names only what's missing (`needs ANTHROPIC_API_KEY`). To keep a broken product from hiding behind a skip, the precondition must be listed in the spec and checked before the system is touched; a product error is always a fail. Skips are never green and never go to implementers.

## Commands

Each returns a short status the caller can branch on. Invoking the next command is the approval: calling `scenarios` means the spec is agreed, calling `tests` means the register is approved; the artifacts record this (`Agreed:` / `Approved:` dates).

| Command | Does | Returns |
|---|---|---|
| `spec` | Derives or revises the contract spec; pins the project name in `black-qat.config.json` on first use | `SPEC_READY`, path, items needing a decision |
| `scenarios` | Writes the register and gaps list, no test code | `SCENARIOS_READY`, count, new ambiguities |
| `tests` | Writes the tests and runs them once; failures must be clean (behavior absent or wrong, never harness errors) | `TESTS_READY` with counts, or `TESTS_BLOCKED` |
| `verify` | Runs the suite; triages failures | totals line, then implementation bugs (behavior-only), spec ambiguities, test defects fixed, couldn't run |
| `open` | Opens the human-readable store files in the user's viewer | one line, no content |

On an existing system, tests that already pass are fine. Since the tester can't read the implementation to rule out vacuous tests, every test must assert on concrete observable output, and already-passing tests are re-checked for that.

## How the hiding is enforced

- **Guard hook (PreToolUse).** Any agent other than the tester, at any depth, is denied calls whose path or command references the store. Only the root session may run the runner and opener, so subagents can't probe the tests by trial and error, and only the root may dispatch the tester. The tester's writes are limited to the store and the spec file. Its read restriction ("never the implementation") is instruction-only: the hook can't know a run's input files, and the critical direction is coder-can't-see-tests.
- **Summary-only runner.** `bq-run` prints one line (`N passed, M failed: IDs; K skipped: IDs (reason)`) and exits 0 / 1 / 3 / 2 (pass / fail / skips only / error). Raw output stays in the store.
- **Report contract.** The tester's report reaches the caller verbatim, so its shape is fixed per mode (status word, counts, decision items, behavior-only bug reports with no IDs). Instructions alone didn't hold: testers kept adding scenario descriptions. A check on the tester's hand-back and a SubagentStop hook bounce any report outside the contract and make the tester resend it. The check is structural: it stops extra lines and IDs, not a leak phrased inside an allowed line.
- **Root-as-coder caveat.** A main session that both writes code and runs `verify` sees summaries and behavior reports across rounds. Still no test code, but weaker isolation than coding in subagents or a separate session. Documented, not prevented.

## Project identity

The store is keyed by project name: `project` in `black-qat.config.json`, else the main checkout's directory name. Every linked git worktree resolves to its main checkout for the suite, spec and config, because a worktree's own folder name would otherwise select a different, empty suite. Runs from a worktree still test that worktree by default. Pinning the name in the config protects against renamed folders and fresh clones.

## Known gaps

Deliberately not handled yet:

- Skips are trusted: nothing checks a skip reason against the spec's required-environment list.
- Bare repositories with worktrees are not supported (the suite's recorded project root won't match).
- A config committed only on a worktree branch is ignored; the main checkout's config wins.
- A report bounced repeatedly is bounded only by Claude Code's own limit on consecutive stop-hook continuations.
- A skip reason containing `(`, `)` or `,` makes the summary line harder to parse.
