# black-qat platform notes

Facts about Claude Code that black-qat relies on, verified by probing rather than assumed. Re-check them when Claude Code changes.

Probed with Claude Code 2.1.323 (`claude -p --plugin-dir <repo> --allowedTools "Bash,Read,Skill,Agent"`, run from a scratch git repo; no permission bypass). Probe hook logged stdin JSON to `<scratchpad>/bq-probe.log` (scratchpad, via `BQ_PROBE_DIR`).

## Q1. agent_type / agent_id seen by the hook

- Plugin agent `black-qat-tester` appears as `"agent_type":"black-qat:black-qat-tester"` (namespaced `<plugin>:<agent>`), with `"agent_id":"a3fd3c46f1ece1744"`.
- Root session events have **neither** `agent_id` nor `agent_type`.

Log excerpts (trimmed):

```
{"session_id":"c69d0d7a-...","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"which bq-probe",...}}                       <- root: no agent_id/agent_type
{"session_id":"c69d0d7a-...","permission_mode":"default","agent_id":"a3fd3c46f1ece1744","agent_type":"black-qat:black-qat-tester","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hi",...}}   <- tester
```

Guard hook should match `agent_type == "black-qat:black-qat-tester"` (consider also accepting bare `black-qat-tester` defensively).

## Q2. Invocation names

- Skill `skills/probe/SKILL.md` is invoked as `black-qat:probe` (`/black-qat:<dir>`); e.g. verify is `/black-qat:verify`.
- Agent dispatch `subagent_type` that worked: `black-qat:black-qat-tester` (the model reported using exactly this and the tester ran `echo hi`).
- Docs: https://code.claude.com/docs/en/plugins/components.md (agent name form `<plugin>:<name>`).

## Q3. Referencing plugin scripts from a skill

- `${CLAUDE_PLUGIN_ROOT}` **is substituted inline in SKILL.md content**: the skill body said `echo ${CLAUDE_PLUGIN_ROOT}`; the Bash hook log shows the command actually run was `echo /Users/<user>/.../black-qat` (already substituted).
- Plugin `bin/` **is on the Bash tool's PATH**: `which bq-probe` resolved to `<plugin root>/bin/bq-probe` (in a root session; docs say it applies to subagents' Bash too). It is appended after the user's PATH entries.
- Docs also state the variables are NOT in the environment of commands run via the Bash tool, so use the inline substitution in skill/agent Markdown, or bare `bin/` commands.
- In hook commands, `${CLAUDE_PLUGIN_ROOT}` works and is also exported to the hook process env (hook ran via `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/log_event.py"`).
- Source: https://code.claude.com/docs/en/plugins-reference (Environment variables, Standard layout).

## Q4. Can a plugin enable sandbox filesystem read-deny?

**No documented way.** The plugin manifest fields (https://code.claude.com/docs/en/plugins-reference) cover skills, commands, agents, hooks, MCP/LSP servers, output styles, themes, monitors, userConfig; there is no settings/sandbox/permissions component. (`network.hosts` is informational only and allows/blocks nothing.) Not independently confirmed by an end-to-end test; the last ~12k characters of the sandboxing page were not read.

Sandbox read-deny is user/project settings (https://code.claude.com/docs/en/sandboxing):

```json
{ "sandbox": { "enabled": true, "filesystem": { "denyRead": ["~/.black-qat"] } } }
```

(`allowRead` re-opens subpaths; narrower path wins.) Caveats from the docs: `denyRead` applies only to sandboxed shell commands; the built-in Read tool is governed by permission rules instead (e.g. a `Read` deny rule). Plugin hooks run outside the sandbox. So the README should document this as **optional user hardening** with the snippet above; the guard hook remains the primary enforcement.

## Q5. Can a hook enforce the shape of a subagent's report? (2026-11-22)

- **SubagentStop** receives `agent_type`, `agent_id`, `stop_hook_active` and `last_assistant_message` (the subagent's final text). Its matcher filters on agent type; plugin agents are matched by the scoped name, anchored: `^black-qat:black-qat-tester$`.
- Returning `{"decision": "block", "reason": ...}` keeps the subagent running and delivers `reason` as its next instruction. Claude Code caps consecutive stop-hook continuations (8 by default).
- **Verified end to end** (headless `claude -p --plugin-dir`, plugin `hooks/hooks.json`): the tester was told to append a scenario list to its report; the SubagentStop hook blocked it with the contract message; the tester resent only the allowed lines; the parent received only those.
- Subagents may instead deliver their report through a **SubagentHandback** tool call, whose `tool_input.message` is the delivered report; `last_assistant_message` then holds only closing text. black-qat checks that path in PreToolUse. Not exercised in the headless run (no handback occurred there); covered by unit tests.
- PostToolUse `updatedToolOutput` can replace a built-in tool's output, but the Agent tool's output shape is undocumented, so black-qat bounces at the source instead of rewriting.
- Source: https://code.claude.com/docs/en/hooks
