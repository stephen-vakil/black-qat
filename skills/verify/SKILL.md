---
name: verify
description: Use when you want to know whether the implementation satisfies the hidden black-box tests, for example after implementing or fixing something, and need totals plus behavior-only reports of what is wrong.
---

# black-qat verify

Run the hidden suite and report. **Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open.**

## Resolve values (as text; no tool call may mention the store path)

1. PROJECT_ROOT: the main checkout, shared by every worktree of the repo: run `git worktree list --porcelain` and take the path after `worktree ` on its first line (fallback: the current directory). CHECKOUT: run `git rev-parse --show-toplevel` (fallback: the current directory); it differs from PROJECT_ROOT only inside a worktree.
2. Project name: `project` from `<PROJECT_ROOT>/black-qat.config.json` if that file exists, else the basename of PROJECT_ROOT.
3. STORE: get the home directory with `echo $HOME` (a command that does not contain the store path), then build STORE as text: `<home>/.black-qat/<project>`. Put it in the dispatch prompt only. Never put the store path in any tool call (Read, Grep, Glob, Bash).
4. SPEC: `<PROJECT_ROOT>/` plus `specPath` from the config if set, else `docs/black-qat/spec.md`.

## Steps

1. Run `bq-run` (add `--target <path>` if the caller named a checkout other than CHECKOUT). First check `command -v bq-run`; then run exactly ONE of `bq-run` or `${CLAUDE_PLUGIN_ROOT}/bin/bq-run`, once. Never chain them with `||` (exit 1 means test failures, not "not found"). It prints one line of totals and exits 0 (all pass), 1 (failures), 2 (error) or 3 (no failures, but some scenarios skipped because required environment is missing). Skips are listed after `;` as `K skipped: <IDs> (<reason>)`.
2. Exit 0: return the totals line.
3. Exit 2: return the error line unchanged.
4. Exit 3: return the **Run summary** and **Couldn't run** sections from step 6. Do not triage skips. Not green.
5. Exit 1: dispatch with the Agent tool, `subagent_type: black-qat:black-qat-tester`, prompt:

```
MODE: triage
PROJECT_ROOT: <PROJECT_ROOT>
STORE: <STORE>
SPEC: <SPEC>
FAILING: <failing IDs from the totals line, never the skipped ones>
TARGET: <the --target path if one was given, else CHECKOUT>
```

   The tester returns `TRIAGE_DONE` and items headed `<ID> — <class>` with an indented body. If it returns `BLOCKED:` or anything malformed, return the run summary plus that line verbatim.
6. Return these labeled sections (omit empty ones after the first):
   - **Run summary (for the caller)**: the totals line as printed, including IDs.
   - **Couldn't run — for the human**: each skip reason with its count (e.g. "3 scenarios need ANTHROPIC_API_KEY"). These were not checked at all; supply what's missing and verify again.
   - **Implementation bugs — forward these to the implementer**: each body only, IDs stripped, no test details.
   - **Spec ambiguities — for the human**: each explanation.
   - **Test defects fixed**: a brief note, no IDs.

   Only the Implementation bugs section is for implementers; never forward the other sections to them.
