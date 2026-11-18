"""The @gate decorator.

    low    -> just run it
    medium -> ask once per session ("always" remembers the yes)
    high   -> ask every single time
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import sys
import threading
from collections.abc import Callable, Iterable
from typing import Any

from . import audit, policy
from .approvers import ApprovalRequest, Decision, terminal_approver
from .policy import RISK_LEVELS

ON_DENY = ("raise", "return")

_prompt_lock = threading.Lock()
_session_lock = threading.Lock()
_session_approved: set[str] = set()
_default_approver: Callable[[ApprovalRequest], Decision | bool] | None = None


class ApprovalDenied(PermissionError):
    """Raised when a gated call is not approved."""

    def __init__(self, tool: str, reason: str):
        self.tool = tool
        self.reason = reason
        super().__init__(f"{tool} was not approved ({reason})")


def set_approver(approver: Callable[[ApprovalRequest], Decision | bool] | None) -> None:
    """Set the approver used by every gate that does not pass its own. None means the terminal."""
    global _default_approver
    _default_approver = approver


def reset_session() -> None:
    """Forget every remembered "always" and reload approval.toml on the next call."""
    with _session_lock:
        _session_approved.clear()
    policy.clear_cache()


def _remembered(key: str) -> bool:
    with _session_lock:
        return key in _session_approved


def _remember(key: str) -> None:
    with _session_lock:
        _session_approved.add(key)


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def denial_message(tool: str, reason: str = "human") -> str:
    who = (
        "no human was available to approve it"
        if reason == "no_human"
        else "it was denied by the human reviewer"
    )
    return (
        f"The action {tool!r} did not run because {who}. "
        "Do not retry it. Ask the user how they want to proceed."
    )


class _Gate:
    def __init__(self, func, *, tool, risk, preview, on_deny, redact, approver):
        self.func = func
        self.tool = tool
        self.key = f"{func.__module__}.{func.__qualname__}"
        self.sig = inspect.signature(func)
        self.risk = risk
        self.preview = preview
        self.on_deny = on_deny
        self.redact = frozenset(redact)
        self.approver = approver

    # ---- helpers -------------------------------------------------------

    def _shown(self, bound: inspect.BoundArguments) -> dict[str, Any]:
        full = self.sig.bind(*bound.args, **bound.kwargs)
        full.apply_defaults()
        return {
            k: (audit.REDACTED if k in self.redact else v) for k, v in full.arguments.items()
        }

    def _preview(self, bound: inspect.BoundArguments) -> str | None:
        if self.preview is None:
            return None
        try:
            return str(self.preview(*bound.args, **bound.kwargs))
        except Exception as exc:  # a broken preview must not block or skip the question
            return f"(preview failed: {type(exc).__name__}: {exc})"

    def _log(self, pol, risk, decision, reason, bound, edited=False):
        full = self.sig.bind(*bound.args, **bound.kwargs)
        full.apply_defaults()
        audit.write(
            audit.resolve_path(pol.audit_log),
            tool=self.tool,
            risk=risk,
            decision=decision,
            reason=reason,
            arguments=dict(full.arguments),
            redact=self.redact,
            edited=edited,
        )

    # ---- the decision --------------------------------------------------

    def quick(self, args, kwargs):
        """Decide without a human if possible.

        Returns (allowed, bound, reason) when settled, or (None, bound, context) when a human is needed.
        """
        bound = self.sig.bind(*args, **kwargs)
        pol = policy.load()
        risk = pol.tier_for(self.tool) or self.risk

        if risk == "low":
            self._log(pol, risk, "allowed", "low_risk", bound)
            return True, bound, "low_risk"
        if risk == "medium" and _remembered(self.key):
            self._log(pol, risk, "allowed", "session", bound)
            return True, bound, "session"

        approver = self.approver or _default_approver or terminal_approver
        if approver is terminal_approver and not _stdin_is_tty():
            allowed = pol.non_interactive == "allow"
            self._log(pol, risk, "allowed" if allowed else "denied", "no_human", bound)
            return allowed, bound, "no_human"

        return None, bound, (pol, risk, approver)

    def ask(self, bound, context):
        pol, risk, approver = context
        note = None
        edited = False
        while True:
            request = ApprovalRequest(
                tool=self.tool,
                risk=risk,
                arguments=self._shown(bound),
                preview=self._preview(bound),
                can_remember=risk == "medium",
                note=note,
            )
            with _prompt_lock:
                # another thread may have said "always" while we waited for the lock
                if risk == "medium" and _remembered(self.key):
                    self._log(pol, risk, "allowed", "session", bound, edited)
                    return True, bound, "session"
                decision = approver(request)

            if isinstance(decision, bool):
                decision = Decision(approved=decision)
            if not isinstance(decision, Decision):
                raise TypeError(f"approver returned {decision!r}, expected a Decision or bool")

            if decision.arguments is not None:
                new_args = dict(decision.arguments)
                # the human only ever saw "***" for redacted fields; keep the real value
                current = self.sig.bind(*bound.args, **bound.kwargs)
                current.apply_defaults()
                for key in self.redact:
                    if new_args.get(key) == audit.REDACTED and key in current.arguments:
                        new_args[key] = current.arguments[key]
                try:
                    bound = self.sig.bind(**new_args)
                except TypeError as exc:
                    note = f"edit rejected: {exc}"
                    continue
                edited = True
                note = "arguments edited, please confirm"
                continue

            if decision.approved and decision.remember and risk == "medium":
                _remember(self.key)
            outcome = "allowed" if decision.approved else "denied"
            self._log(pol, risk, outcome, "human", bound, edited)
            return decision.approved, bound, "human"

    def deny(self, reason):
        if self.on_deny == "return":
            return denial_message(self.tool, reason)
        raise ApprovalDenied(self.tool, reason)


def gate(
    risk: str | Callable = "high",
    preview: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    on_deny: str = "raise",
    redact: Iterable[str] = (),
    approver: Callable[[ApprovalRequest], Decision | bool] | None = None,
):
    """Pause a function for human approval before it runs.

    risk      "low", "medium" or "high" (approval.toml can override it)
    preview   called with the same arguments; returns text describing the real effect
    name      tool name used in the prompt, policy file and audit log (default: function name)
    on_deny   "raise" raises ApprovalDenied, "return" returns a message for the model instead
    redact    argument names to mask in the prompt and audit log
    approver  custom approver for this tool (default: set_approver() or the terminal)
    """
    if callable(risk):  # bare @gate
        return gate()(risk)
    if risk not in RISK_LEVELS:
        raise ValueError(f"risk should be one of {RISK_LEVELS}, got {risk!r}")
    if on_deny not in ON_DENY:
        raise ValueError(f"on_deny should be one of {ON_DENY}, got {on_deny!r}")
    if isinstance(redact, str):
        redact = (redact,)

    def decorator(func):
        g = _Gate(
            func,
            tool=name or func.__name__,
            risk=risk,
            preview=preview,
            on_deny=on_deny,
            redact=redact,
            approver=approver,
        )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                allowed, bound, context = g.quick(args, kwargs)
                if allowed is None:
                    # the prompt blocks, so keep it off the event loop
                    allowed, bound, context = await asyncio.to_thread(g.ask, bound, context)
                if not allowed:
                    return g.deny(context)
                return await func(*bound.args, **bound.kwargs)

            async_wrapper.__gate__ = g
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            allowed, bound, context = g.quick(args, kwargs)
            if allowed is None:
                allowed, bound, context = g.ask(bound, context)
            if not allowed:
                return g.deny(context)
            return func(*bound.args, **bound.kwargs)

        wrapper.__gate__ = g
        return wrapper

    return decorator
