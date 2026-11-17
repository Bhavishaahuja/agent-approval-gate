# Build plan: v0.1.0

Goal: ship everything the README promises. That means risk tiers, previews, remembered decisions, edit args, a policy file, an audit log and a demo, with no runtime dependencies.

## Decisions

1. **"Always" is not offered on high risk.** High asks every time. Allowing "always" there would quietly bring back approval fatigue.
2. **A denial raises `ApprovalDenied` by default.** It is a subclass of `PermissionError`, so existing handlers still catch it. `on_deny="return"` hands the model a message instead, so the agent loop keeps going.
3. **`approval.toml` beats the tier in code.** Ops can tighten a tool without a code change.
4. **Arguments go in the audit log.** Values are shortened, and fields named in `redact=` are masked.

## Steps

- [x] **1. Scaffold.** Package layout, CI on 3.11 to 3.13, PyPI trusted publishing.
- [x] **2. Basic gate.** Low runs, high asks, and with no terminal it denies.
- [x] **3. Session memory.** Decisions remembered in memory for the life of the process, keyed by the function's qualified name. Medium asks once per session. `reset_session()` clears it. A lock keeps prompts from two threads from overlapping.
- [x] **4. Prompt and answers.** The prompt shows the tool, the risk tier, the arguments and the preview. Answers are `y` (once), `n` (the default), `a` (always this session, medium only) and `e` (edit the arguments). If the preview function fails, the prompt says so and still asks. Denials raise `ApprovalDenied(PermissionError)`.
- [x] **5. Edit arguments.** The arguments are shown as JSON and the user types replacement JSON. It is checked with `inspect.signature().bind`, then the preview runs again and the gate asks again.
- [x] **6. `approval.toml`.** Read with stdlib `tomllib`, from the current directory or the path in `AGENT_APPROVAL_GATE_POLICY`. `[tools]` maps names or wildcard patterns to a tier. `[defaults]` sets `non_interactive` and `audit_log`.
- [x] **7. Audit log.** One JSON line per decision with time, tool, tier, decision, reason and arguments. Arguments are shortened, and keys listed in `redact=` are masked.
- [x] **8. Framework compatibility.** `async def` tools work. Signature, docstring and annotations survive the wrapper, so LangChain and OpenAI Agents can build tool schemas from it. `on_deny="raise" | "return"`.
- [x] **9. Pluggable approver.** `gate(..., approver=fn)` and `set_approver(fn)`. The terminal prompt is just the built-in approver. This leaves room for Slack or phone approvals later.
- [x] **10. Tests.** Every tier × answer, terminal vs no terminal, policy, audit, edit, async and threading.
- [x] **11. `demo` command.** A scripted fake agent in a temporary folder with three tools: `read_file` (low), `rename_file` (medium) and `delete_files` (high, with a preview). It prints the audit log at the end.
- [ ] **12. Release.** Record the GIF (`vhs demo/demo.tape`), check the comparison table against current framework docs, bump to 0.1.0 and tag `v0.1.0` to publish.

## Later (not v0.1)

- Slack and phone approvers, built on the approver hook.
- Async approvers.
- A `never` tier in the policy file to block a tool outright.
