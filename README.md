# agent-approval-gate: human approval for AI agent tool calls, without approval fatigue

Pause risky AI agent actions for a human yes or no. A plain Python decorator with risk tiers, previews of what is about to happen, remembered decisions and an audit log. Works with LangChain, the OpenAI Agents SDK, or your own loop, because it wraps plain functions.

> Approval prompts fail when you see 40 a day. This one only asks when it matters.

<!-- TODO: demo GIF here (under 20 seconds). Record with: vhs demo/demo.tape -->
![demo](demo/demo.gif)

## Quickstart

```bash
uvx agent-approval-gate demo     # try it with nothing installed
pip install agent-approval-gate  # add it to your project
```

```python
from agent_approval_gate import gate

def show_files_to_delete(folder):
    return f"about to delete everything in {folder}"

@gate(risk="high", preview=show_files_to_delete)
def delete_files(folder):
    ...
```

<!-- TODO: paste real terminal output from the demo here -->

## Q&A

**What is this?** A decorator that stops an AI agent before it runs a risky function and asks a human to approve it.

**Who is it for?** Anyone building agents that can delete, send, pay or deploy things.

**How is it different from LangChain or OpenAI Agents SDK approvals?** Those pause. This one also handles fatigue: risk tiers, "always for this session", previews of the real effect, a policy file and an audit log. And it is framework-free.

**What happens in CI or cron when nobody is there to answer?** It denies and logs. Safe by default.

**Does it send data anywhere?** No. Everything stays local. No network calls.

## Compared to

| | agent-approval-gate | Framework built-in approval | Hand-rolled `input()` |
|---|---|---|---|
| Works with any framework | yes | no | yes |
| Risk tiers | yes | no | no |
| Remember "yes" for the session | yes | partial | no |
| Preview of the real effect | yes | no | no |
| Audit log | yes | no | no |
| Safe default with no human present | yes | varies | no (hangs) |

<!-- TODO: double check the middle column against current docs before launch -->

## How it works

1. `@gate` wraps your function.
2. On each call it looks up the risk tier (code, or `approval.toml` if present).
3. Low runs. Medium asks once per session. High asks every time.
4. The prompt shows your preview text and offers yes / no / always / edit args.
5. The decision is appended to `approval_audit.jsonl`.

## Limits

- Terminal prompts only in v1. Slack and phone approvals come later if people want them.
- It gates the functions you decorate. It cannot see tool calls you do not wrap.

## Also in this series

<!-- TODO: link the other tiny tools once they are live -->

## License

MIT
