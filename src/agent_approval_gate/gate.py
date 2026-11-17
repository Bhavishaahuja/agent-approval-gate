import functools
import sys

# the three tiers from the plan:
#   low    -> just run it
#   medium -> ask once per session (TODO step 3)
#   high   -> ask every single time
RISK_LEVELS = ("low", "medium", "high")


def _ask_human(func_name, preview_text):
    # no terminal means no human (CI, cron, background job), so deny
    if not sys.stdin.isatty():
        return False

    print(f"\n[approval needed] {func_name}")
    if preview_text:
        print(preview_text)
    answer = input("run it? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def gate(risk="high", preview=None):
    if risk not in RISK_LEVELS:
        raise ValueError(f"risk should be one of {RISK_LEVELS}, got {risk!r}")

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if risk == "low":
                return func(*args, **kwargs)

            preview_text = preview(*args, **kwargs) if preview else None
            # TODO step 3: medium should remember a "yes" for the session
            # TODO step 5: "edit the arguments" answer
            # TODO step 6: approval.toml overrides
            # TODO step 7: write every decision to the audit log
            if _ask_human(func.__name__, preview_text):
                return func(*args, **kwargs)
            raise PermissionError(f"{func.__name__} was not approved")

        return wrapper

    return decorator
