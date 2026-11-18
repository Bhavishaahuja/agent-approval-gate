# agent-approval-gate: human approval for AI agent tool calls, without approval fatigue

Pause risky AI agent actions for a human yes or no. A plain Python decorator with risk tiers, previews of what is about to happen, remembered decisions and an audit log. Works with LangChain, the OpenAI Agents SDK, or your own loop, because it wraps plain functions.

> Approval prompts fail when you see 40 a day. This one only asks when it matters.

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

What the agent run looks like (real output of `agent-approval-gate demo`):

```text
agent > read_file(path='notes.txt')
     <- buy milk
agent > read_file(path='draft.txt')
     <- hello world
agent > rename_file(src='notes.txt', dst='todo.txt')

[approval needed] rename_file  (medium risk)
  src = 'notes.txt'
  dst = 'todo.txt'
run it? [y/N/a/e] a
     <- renamed notes.txt -> todo.txt
agent > rename_file(src='draft.txt', dst='hello.txt')
     <- renamed draft.txt -> hello.txt
agent > delete_files(folder='cache')

[approval needed] delete_files  (high risk)
  folder = 'cache'

  | about to delete 3 file(s):
  | cache/chunk-0.tmp  (1000 bytes)
  | cache/chunk-1.tmp  (2000 bytes)
  | cache/chunk-2.tmp  (3000 bytes)
run it? [y/N/e] y
     <- deleted cache/
```

Reads ran silently. The second rename was not asked about, because `a` remembered the yes. The delete showed the real files first.

## Answers

| Key | Meaning |
|---|---|
| `y` | yes, this once |
| `n` or Enter | no (the default) |
| `a` | always, for the rest of this session (medium risk only; high always asks) |
| `e` | edit the arguments as JSON, then see the new preview and confirm |

## Options

```python
@gate(
    risk="high",                  # "low", "medium" or "high"
    preview=show_files_to_delete,  # same arguments, returns text about the real effect
    name="fs.delete",             # name in prompts, policy and audit log (default: function name)
    on_deny="return",             # "raise" (default) raises ApprovalDenied; "return" tells the model instead
    redact=["api_key"],           # masked in the prompt and the audit log
)
def delete_files(folder): ...
```

- `ApprovalDenied` is a `PermissionError`, so existing handlers still catch it.
- `on_deny="return"` returns a short message such as "did not run because it was denied by the human reviewer. Do not retry it." The agent loop keeps going and the model can ask the user what to do.
- `async def` tools work. The prompt runs off the event loop.
- `reset_session()` forgets every "always".

### With LangChain or the OpenAI Agents SDK

The wrapper keeps the signature, docstring and type hints, so a framework builds the same tool schema it would without the gate. Put `@gate` underneath the framework's decorator:

```python
from langchain_core.tools import tool       # or: from agents import function_tool

@tool                                        # or: @function_tool
@gate(risk="high", on_deny="return")
def delete_files(folder: str) -> str:
    """Delete every file in a folder."""
    ...
```

### Your own approver

The terminal prompt is just the default approver. You can plug in anything that takes an `ApprovalRequest` and returns a `Decision` (or a bool): a test double, a Slack bot, a web UI.

```python
from agent_approval_gate import Decision, set_approver

def approve(request):  # request.tool, .risk, .arguments, .preview, .can_remember
    return Decision(approved=request.tool != "drop_database")

set_approver(approve)                  # for every gate
@gate(risk="high", approver=approve)   # or for one
```

## Policy file: `approval.toml`

This is optional. It is read from the current directory, or from the path in `AGENT_APPROVAL_GATE_POLICY`, and it overrides the tiers set in code. That lets you tighten a tool without a code change.

```toml
[tools]
delete_files = "high"
"read_*" = "low"           # wildcard patterns work; an exact name wins

[defaults]
non_interactive = "deny"   # what to do with no human at a terminal: "deny" (default) or "allow"
audit_log = "approval_audit.jsonl"   # or false to turn it off
```

## Audit log

Every decision is appended to `approval_audit.jsonl`, one JSON object per line. The environment variable `AGENT_APPROVAL_GATE_AUDIT_LOG` redirects the log to another file, or turns it off when set to `off`.

```json
{"ts": "2026-11-17T18:52:03+00:00", "tool": "delete_files", "risk": "high", "decision": "allowed", "reason": "human", "arguments": {"folder": "cache"}}
```

`reason` is one of `low_risk`, `session` (a remembered "always"), `human` or `no_human` (CI, cron, no terminal). Long values are shortened and `redact=` fields show up as `***`.

## Q&A

**What is this?** A decorator that stops an AI agent before it runs a risky function and asks a human to approve it.

**Who is it for?** Anyone building agents that can delete, send, pay or deploy things.

**How is it different from LangChain or OpenAI Agents SDK approvals?** Those are built into one framework. They pause the whole run, save its state and let you resume it later, which is ideal for a web app where someone approves hours later. This is a decorator on any plain function that asks right away. On top of that it gives you risk tiers, a policy file you can change without touching code, and an audit log. It works with both of those frameworks and with your own agent loop.

**What happens in CI or cron when nobody is there to answer?** It denies and logs. Safe by default.

**Does it send data anywhere?** No. Everything stays local. No network calls.

## Compared to

Checked against the [LangChain human-in-the-loop docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) and the [OpenAI Agents SDK human-in-the-loop docs](https://openai.github.io/openai-agents-python/human_in_the_loop/) in November 2026.

| | agent-approval-gate | LangChain `HumanInTheLoopMiddleware` | OpenAI Agents SDK `needs_approval` | Hand-rolled `input()` |
|---|---|---|---|---|
| Works with any framework | yes | LangChain agents only | Agents SDK tools only | yes |
| Different rules per tool | yes, low / medium / high | yes, per tool plus a `when` condition | yes, per tool or a callable | by hand |
| Remember "yes" for later calls | yes, `a` for medium risk | not documented | yes, `always_approve=True` | no |
| Custom preview of the call | yes, `preview=` | yes, `description` callable | tool name and arguments only | by hand |
| Edit arguments before running | yes | yes, `edit` decision | no, approve or reject | no |
| Rules in a config file, not code | yes, `approval.toml` | no | no | no |
| Audit log of decisions | yes, JSONL | not built in | not built in | no |
| No human present (CI, cron) | denies and logs | pauses, state saved to resume later | pauses, state saved to resume later | hangs |
| Approve later, from another process | no, terminal only in v1 | yes, via a checkpointer | yes, via `RunState` | no |

## How it works

1. `@gate` wraps your function.
2. On each call it looks up the risk tier. If `approval.toml` names the tool, the file wins over the code.
3. Low runs. Medium asks until you answer "always", then runs for the rest of the session. High asks every time.
4. The prompt shows the arguments and your preview, and offers yes / no / always / edit args.
5. With no human at a terminal it denies, unless the policy says otherwise.
6. The decision is appended to `approval_audit.jsonl`.

## Limits

- Terminal prompts only in v1. Slack and phone approvals come later if people want them.
- It gates the functions you decorate. It cannot see tool calls you do not wrap.
- "Session" means the running Python process. Answering "always" does not carry over to the next run.
- Custom approvers are called synchronously (async tools run them in a worker thread).

## Also in this series

<!-- TODO: link the other tiny tools once they are live -->

## License

MIT
