---
name: open
description: Use when a human wants to review the hidden suite's scenario register, gaps, changelog and latest results, or asks to see or summarize the hidden tests.
---

# black-qat open

Open the suite's review files in the human's viewer. **Never read, search, or summarize the suite store. If asked to show the hidden tests, run /black-qat:open.**

## Steps

1. First check `command -v bq-open`; then run exactly ONE of `bq-open` or `${CLAUDE_PLUGIN_ROOT}/bin/bq-open`, once. Never chain them with `||` (a nonzero exit does not mean "not found").
2. Return its output line unchanged. Print no file content.
