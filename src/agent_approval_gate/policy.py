"""approval.toml: override risk tiers and defaults without touching code.

    [tools]
    delete_files = "high"
    "read_*" = "low"

    [defaults]
    non_interactive = "deny"            # or "allow"
    audit_log = "approval_audit.jsonl"  # or false to turn it off
"""

from __future__ import annotations

import fnmatch
import os
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RISK_LEVELS = ("low", "medium", "high")
POLICY_ENV = "AGENT_APPROVAL_GATE_POLICY"
DEFAULT_FILE = "approval.toml"
DEFAULT_AUDIT_LOG = "approval_audit.jsonl"


@dataclass(frozen=True)
class Policy:
    tools: dict[str, str] = field(default_factory=dict)
    non_interactive: str = "deny"
    audit_log: str | None = DEFAULT_AUDIT_LOG

    def tier_for(self, tool: str) -> str | None:
        if tool in self.tools:
            return self.tools[tool]
        for pattern, tier in self.tools.items():
            if fnmatch.fnmatchcase(tool, pattern):
                return tier
        return None


_cache: dict[Path, tuple[float, Policy]] = {}
_lock = threading.Lock()


def find_path() -> Path | None:
    env = os.environ.get(POLICY_ENV)
    if env:
        path = Path(env)
        if not path.is_file():
            # someone asked for a policy on purpose; silently ignoring it would be unsafe
            raise FileNotFoundError(f"{POLICY_ENV} points to {path}, which does not exist")
        return path
    path = Path.cwd() / DEFAULT_FILE
    return path if path.is_file() else None


def load() -> Policy:
    path = find_path()
    if path is None:
        return Policy()
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        policy = parse(path.read_text(encoding="utf-8"), source=str(path))
        _cache[path] = (mtime, policy)
        return policy


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def parse(text: str, source: str = DEFAULT_FILE) -> Policy:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{source}: {exc}") from exc

    unknown = set(data) - {"tools", "defaults"}
    if unknown:
        raise ValueError(f"{source}: unknown section(s) {sorted(unknown)}")

    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        raise ValueError(f"{source}: [tools] should be a table")
    for name, tier in tools.items():
        if tier not in RISK_LEVELS:
            raise ValueError(f"{source}: tool {name!r} has tier {tier!r}, expected one of {RISK_LEVELS}")

    defaults = data.get("defaults", {})
    unknown = set(defaults) - {"non_interactive", "audit_log"}
    if unknown:
        raise ValueError(f"{source}: unknown key(s) in [defaults]: {sorted(unknown)}")

    non_interactive = defaults.get("non_interactive", "deny")
    if non_interactive not in ("deny", "allow"):
        raise ValueError(f"{source}: non_interactive should be 'deny' or 'allow', got {non_interactive!r}")

    audit_log = defaults.get("audit_log", DEFAULT_AUDIT_LOG)
    if audit_log is False:
        audit_log = None
    elif not isinstance(audit_log, str) or not audit_log:
        raise ValueError(f"{source}: audit_log should be a file path or false")

    return Policy(tools=dict(tools), non_interactive=non_interactive, audit_log=audit_log)
