---
name: agent-approval-gate
description: Use when writing AI agent code that has tools which delete, send, pay, deploy or overwrite anything. Wraps those tools with a human approval gate.
---

# agent-approval-gate

When you write or edit agent code, find every tool function that can cause damage that is hard to undo
(deleting files, sending email or messages, moving money, deploying, dropping tables, overwriting data).

For each one:

1. Make sure `agent-approval-gate` is in the project dependencies.
2. Add `from agent_approval_gate import gate` at the top of the file.
3. Decorate it with `@gate(risk=...)`:
   - `low` for read-only tools (or just leave them alone)
   - `medium` for reversible writes
   - `high` for anything destructive, external or costly
4. Where you can, pass `preview=` a small function that takes the same arguments and returns a short
   human readable description of the real effect (for example the list of files about to be deleted).

Do not gate read-only tools as high. Too many prompts is how people end up approving everything blindly.
