import argparse

from . import __version__


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
        # TODO step 11: tiny agent with a read tool and a delete tool
        print("demo is not built yet, check back soon")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
