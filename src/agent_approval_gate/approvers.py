"""Approvers decide whether a gated call may run.

An approver is any callable that takes an ``ApprovalRequest`` and returns a
``Decision`` (or a plain bool). The terminal prompt below is the built-in one;
Slack, phone or test approvers plug in the same way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    risk: str
    arguments: dict[str, Any]
    preview: str | None = None
    # True when "always for this session" is allowed (medium risk only)
    can_remember: bool = False
    # extra line for the human, e.g. why an edit was rejected
    note: str | None = None


@dataclass(frozen=True)
class Decision:
    approved: bool = False
    # remember the "yes" for the rest of the session (ignored unless allowed)
    remember: bool = False
    # replacement arguments; the gate validates them, reruns the preview and asks again
    arguments: dict[str, Any] | None = field(default=None)


def _short(value: Any, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def terminal_approver(request: ApprovalRequest) -> Decision:
    """Ask on the terminal. Empty answer or end of input means no."""
    print(f"\n[approval needed] {request.tool}  ({request.risk} risk)")
    for key, value in request.arguments.items():
        print(f"  {key} = {_short(value)}")
    if request.preview:
        print()
        for line in str(request.preview).splitlines():
            print(f"  | {line}")
    if request.note:
        print(f"  ! {request.note}")

    choices = "y/N/a/e" if request.can_remember else "y/N/e"
    while True:
        try:
            answer = input(f"run it? [{choices}] ").strip().lower()
        except EOFError:
            return Decision(approved=False)

        if answer in ("", "n", "no"):
            return Decision(approved=False)
        if answer in ("y", "yes"):
            return Decision(approved=True)
        if answer in ("a", "always") and request.can_remember:
            return Decision(approved=True, remember=True)
        if answer in ("e", "edit"):
            current = json.dumps(request.arguments, default=repr)
            print(f"  current: {current}")
            try:
                raw = input("  new arguments as JSON (blank to cancel): ").strip()
            except EOFError:
                return Decision(approved=False)
            if not raw:
                continue
            try:
                new_args = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"  ! not valid JSON: {exc}")
                continue
            if not isinstance(new_args, dict):
                print('  ! expected a JSON object, like {"folder": "tmp"}')
                continue
            return Decision(arguments=new_args)

        valid = "y, n, a or e" if request.can_remember else "y, n or e"
        print(f"  please answer {valid}")
