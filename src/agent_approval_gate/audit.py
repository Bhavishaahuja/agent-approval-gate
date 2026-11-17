"""Append-only JSONL audit log: one line per gate decision."""

from __future__ import annotations

import json
import os
import threading
import warnings
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

AUDIT_ENV = "AGENT_APPROVAL_GATE_AUDIT_LOG"
_OFF = ("", "0", "off", "false", "none")
_lock = threading.Lock()

MAX_STR = 200
MAX_ITEMS = 20
REDACTED = "***"


def resolve_path(policy_path: str | None) -> str | None:
    """The env var wins over approval.toml, so a single run can redirect or disable logging."""
    env = os.environ.get(AUDIT_ENV)
    if env is not None:
        return None if env.strip().lower() in _OFF else env
    return policy_path


def clean(value: Any, redact: frozenset[str] = frozenset(), depth: int = 0) -> Any:
    """Make a value small, JSON-safe and free of redacted fields."""
    if depth > 4:
        return "..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_STR else value[: MAX_STR - 3] + "..."
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_ITEMS:
                out["..."] = f"{len(value) - MAX_ITEMS} more"
                break
            key = str(k)
            out[key] = REDACTED if key in redact else clean(v, redact, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        out = [clean(v, redact, depth + 1) for v in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            out.append(f"... {len(items) - MAX_ITEMS} more")
        return out
    return clean(repr(value), redact, depth)


def write(
    path: str | None,
    *,
    tool: str,
    risk: str,
    decision: str,
    reason: str,
    arguments: dict[str, Any],
    redact: Iterable[str] = (),
    edited: bool = False,
) -> None:
    if not path:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "risk": risk,
        "decision": decision,
        "reason": reason,
        "arguments": clean(arguments, frozenset(redact)),
    }
    if edited:
        record["edited"] = True
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            # a broken log should be loud, but it should not take the agent down with it
            warnings.warn(f"agent-approval-gate could not write audit log {path}: {exc}", stacklevel=3)
