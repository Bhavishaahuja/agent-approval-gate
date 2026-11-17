import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from . import __version__


def run_demo() -> int:
    """A tiny scripted 'agent' in a throwaway folder, so you can feel the three tiers."""
    from . import audit, policy
    from .gate import gate, reset_session

    root = Path(tempfile.mkdtemp(prefix="approval-gate-demo-"))
    saved_env = {k: os.environ.get(k) for k in (audit.AUDIT_ENV, policy.POLICY_ENV)}
    try:
        (root / "notes.txt").write_text("buy milk\nship v0.1\n")
        (root / "draft.txt").write_text("hello world\n")
        (root / "cache").mkdir()
        for i in range(3):
            (root / "cache" / f"chunk-{i}.tmp").write_text("x" * (1000 * (i + 1)))

        log_path = root / "approval_audit.jsonl"
        empty_policy = root / "approval.toml"
        empty_policy.write_text("")
        os.environ[audit.AUDIT_ENV] = str(log_path)
        os.environ[policy.POLICY_ENV] = str(empty_policy)  # ignore any approval.toml in your cwd
        reset_session()

        def list_folder(folder):
            files = sorted(p for p in (root / folder).rglob("*") if p.is_file())
            lines = [f"{p.relative_to(root)}  ({p.stat().st_size} bytes)" for p in files]
            return f"about to delete {len(files)} file(s):\n" + "\n".join(lines)

        @gate(risk="low")
        def read_file(path):
            return (root / path).read_text().splitlines()[0]

        @gate(risk="medium", on_deny="return")
        def rename_file(src, dst):
            (root / src).rename(root / dst)
            return f"renamed {src} -> {dst}"

        @gate(risk="high", preview=list_folder, on_deny="return")
        def delete_files(folder):
            shutil.rmtree(root / folder)
            return f"deleted {folder}/"

        steps = [
            (read_file, {"path": "notes.txt"}),
            (read_file, {"path": "draft.txt"}),
            (rename_file, {"src": "notes.txt", "dst": "todo.txt"}),
            (rename_file, {"src": "draft.txt", "dst": "hello.txt"}),
            (delete_files, {"folder": "cache"}),
        ]

        print(f"demo agent working in {root}")
        print("low runs silently, medium asks once (try 'a'), high asks every time\n")
        for tool, kwargs in steps:
            shown = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            print(f"agent > {tool.__name__}({shown})")
            print(f"     <- {tool(**kwargs)}")

        print("\naudit log (approval_audit.jsonl):")
        if log_path.exists():
            for line in log_path.read_text().splitlines():
                rec = json.loads(line)
                print(f"  {rec['tool']:<13} {rec['risk']:<7} {rec['decision']:<8} {rec['reason']}")
        return 0
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_session()
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="agent-approval-gate",
        description="Human approval for AI agent tool calls.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("demo", help="run a tiny fake agent so you can feel the prompts")
    args = parser.parse_args(argv)

    if args.command == "demo":
        return run_demo()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
