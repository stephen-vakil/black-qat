---
name: scenarios
description: Use when the visible spec is agreed and you want black-qat to write the scenario register (SCENARIOS.md) for review, or to revise it after review. Calling this means the spec is agreed.
---

# black-qat scenarios

Write or revise the scenario register (no test code). **Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open.**

## Resolve values (as text; no tool call may mention the store path)

1. PROJECT_ROOT: the main checkout, shared by every worktree of the repo: run `git worktree list --porcelain` and take the path after `worktree ` on its first line (fallback: the current directory). CHECKOUT: run `git rev-parse --show-toplevel` (fallback: the current directory); it differs from PROJECT_ROOT only inside a worktree.
2. Project name: `project` from `<PROJECT_ROOT>/black-qat.config.json` if that file exists, else the basename of PROJECT_ROOT.
3. STORE: get the home directory with `echo $HOME` (a command that does not contain the store path), then build STORE as text: `<home>/.black-qat/<project>`. Put it in the dispatch prompt only. Never put the store path in any tool call (Read, Grep, Glob, Bash).
4. SPEC: `<PROJECT_ROOT>/` plus `specPath` from the config if set, else `docs/black-qat/spec.md`.

## Steps

1. Dispatch with the Agent tool, `subagent_type: black-qat:black-qat-tester`, prompt:

```
MODE: scenarios
PROJECT_ROOT: <PROJECT_ROOT>
STORE: <STORE>
SPEC: <SPEC>
REVISION NOTES: <review feedback on the existing register; omit if none>
```
2. Return only the defined fields: `SCENARIOS_READY`, the count, the review-with-open hint, and new ambiguities; drop any other prose. If it returns `BLOCKED: ...`, return that line.
