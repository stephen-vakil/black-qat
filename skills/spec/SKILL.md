---
name: spec
description: Use when you have a conversation, PRD, plan or spec and want black-qat to derive or revise the visible contract spec that the hidden tests are built from.
---

# black-qat spec

Derive or revise the contract spec. **Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open.**

## Resolve values (as text; no tool call may mention the store path)

1. PROJECT_ROOT: run `git rev-parse --show-toplevel` (fallback: the current directory).
2. Project name: `project` from `<PROJECT_ROOT>/black-qat.config.json` if that file exists, else the basename of PROJECT_ROOT.
3. STORE: get the home directory with `echo $HOME` (a command that does not contain the store path), then build STORE as text: `<home>/.black-qat/<project>`. Put it in the dispatch prompt only. Never put the store path in any tool call (Read, Grep, Glob, Bash).
4. SPEC: `<PROJECT_ROOT>/` plus `specPath` from the config if set, else `docs/black-qat/spec.md`.

## Steps

1. If the input is a conversation (not files), write it to `<PROJECT_ROOT>/docs/black-qat/inputs/<YYYY-MM-DD>-conversation.md` (create the directory) and use that path as the input.
2. Dispatch with the Agent tool, `subagent_type: black-qat:black-qat-tester`, prompt:

```
MODE: spec
PROJECT_ROOT: <PROJECT_ROOT>
STORE: <STORE>
SPEC: <SPEC>
INPUTS: <input file path(s), one per line>
REVISION NOTES: <decisions on proposed/inferred items, corrections; omit if none>
```
3. Return the tester's result verbatim: `SPEC_READY` first, then the spec path, then the `Needs decision:` list. If the tester returns `BLOCKED: ...`, return that line.
