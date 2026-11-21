---
name: tests
description: Use when the scenario register has been reviewed and approved and you want black-qat to write the hidden tests and run them once. Calling this means the register is approved.
---

# black-qat tests

Write the hidden suite and run it once. **Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open.**

## Resolve values (as text; no tool call may mention the store path)

1. PROJECT_ROOT: run `git rev-parse --show-toplevel` (fallback: the current directory).
2. Project name: `project` from `<PROJECT_ROOT>/black-qat.config.json` if that file exists, else the basename of PROJECT_ROOT.
3. STORE: get the home directory with `echo $HOME` (a command that does not contain the store path), then build STORE as text: `<home>/.black-qat/<project>`. Put it in the dispatch prompt only. Never put the store path in any tool call (Read, Grep, Glob, Bash).
4. SPEC: `<PROJECT_ROOT>/` plus `specPath` from the config if set, else `docs/black-qat/spec.md`.

## Steps

1. Dispatch with the Agent tool, `subagent_type: black-qat:black-qat-tester`, prompt:

```
MODE: tests
PROJECT_ROOT: <PROJECT_ROOT>
STORE: <STORE>
SPEC: <SPEC>
TARGET: <path to the checkout under test; omit to use PROJECT_ROOT>
```
2. Return only the status line (`TESTS_READY`) and the counts line, or `TESTS_BLOCKED` and its reason; drop any other prose. Tests that already pass are reported, not blocking.
