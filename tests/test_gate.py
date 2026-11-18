import asyncio
import inspect
import json
import threading
from pathlib import Path

import pytest

from agent_approval_gate import (
    ApprovalDenied,
    Decision,
    gate,
    reset_session,
    set_approver,
)


def audit_lines(path="approval_audit.jsonl"):
    p = Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def tty(monkeypatch, answers):
    """Pretend there is a human at a terminal typing these answers."""
    it = iter(answers)
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(it)

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", fake_input)
    return prompts


# ---- basics ------------------------------------------------------------


def test_low_risk_runs_without_asking():
    @gate(risk="low")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_high_risk_denied_when_no_human(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    @gate(risk="high")
    def nuke():
        return "boom"

    with pytest.raises(PermissionError):
        nuke()
    assert audit_lines()[-1]["reason"] == "no_human"


def test_high_risk_runs_when_human_says_yes(monkeypatch):
    tty(monkeypatch, ["y"])

    @gate(risk="high", preview=lambda folder: f"deleting {folder}")
    def delete_files(folder):
        return f"deleted {folder}"

    assert delete_files("tmp") == "deleted tmp"


def test_empty_answer_means_no(monkeypatch):
    tty(monkeypatch, [""])

    @gate(risk="high")
    def nuke():
        return "boom"

    with pytest.raises(ApprovalDenied) as exc:
        nuke()
    assert exc.value.tool == "nuke"
    assert exc.value.reason == "human"


def test_eof_means_no(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def eof(_=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    @gate(risk="high")
    def nuke():
        return "boom"

    with pytest.raises(ApprovalDenied):
        nuke()


def test_unknown_answer_asks_again(monkeypatch, capsys):
    tty(monkeypatch, ["maybe", "y"])

    @gate(risk="high")
    def nuke():
        return "boom"

    assert nuke() == "boom"
    assert "please answer" in capsys.readouterr().out


def test_bad_risk_level():
    with pytest.raises(ValueError):
        gate(risk="spicy")


def test_bad_on_deny():
    with pytest.raises(ValueError):
        gate(on_deny="explode")


def test_keeps_function_name():
    @gate(risk="low")
    def my_tool():
        pass

    assert my_tool.__name__ == "my_tool"


def test_bare_decorator_is_high_risk(scripted):
    s = scripted(False)

    @gate
    def nuke():
        return "boom"

    set_approver(s)
    with pytest.raises(ApprovalDenied):
        nuke()
    assert s.requests[0].risk == "high"


# ---- tiers and session memory ------------------------------------------


def test_medium_always_is_remembered(scripted):
    s = scripted(Decision(approved=True, remember=True))
    calls = []

    @gate(risk="medium", approver=s)
    def rename(src):
        calls.append(src)

    rename("a")
    rename("b")
    rename("c")
    assert calls == ["a", "b", "c"]
    assert len(s.requests) == 1
    assert [r["reason"] for r in audit_lines()] == ["human", "session", "session"]


def test_medium_plain_yes_is_not_remembered(scripted):
    s = scripted(True, True)

    @gate(risk="medium", approver=s)
    def rename(src):
        return src

    rename("a")
    rename("b")
    assert len(s.requests) == 2


def test_medium_terminal_offers_always(monkeypatch):
    prompts = tty(monkeypatch, ["a"])

    @gate(risk="medium")
    def rename(src):
        return src

    assert rename("a") == "a"
    assert rename("b") == "b"  # no second answer needed
    assert prompts == ["run it? [y/N/a/e] "]


def test_high_never_remembers(scripted):
    s = scripted(Decision(approved=True, remember=True), True)

    @gate(risk="high", approver=s)
    def nuke():
        return "boom"

    nuke()
    nuke()
    assert len(s.requests) == 2
    assert s.requests[0].can_remember is False


def test_high_terminal_rejects_always(monkeypatch, capsys):
    prompts = tty(monkeypatch, ["a", "n"])

    @gate(risk="high")
    def nuke():
        return "boom"

    with pytest.raises(ApprovalDenied):
        nuke()
    assert prompts[0] == "run it? [y/N/e] "
    assert "please answer y, n or e" in capsys.readouterr().out


def test_reset_session_forgets(scripted):
    s = scripted(Decision(approved=True, remember=True), False)

    @gate(risk="medium", approver=s)
    def rename():
        return "ok"

    rename()
    reset_session()
    with pytest.raises(ApprovalDenied):
        rename()


def test_session_is_per_function(scripted):
    s = scripted(Decision(approved=True, remember=True), True)

    @gate(risk="medium", approver=s)
    def one():
        pass

    @gate(risk="medium", approver=s)
    def two():
        pass

    one()
    two()
    assert len(s.requests) == 2


# ---- prompt contents ---------------------------------------------------


def test_preview_and_arguments_reach_approver(scripted):
    s = scripted(True)

    @gate(risk="high", preview=lambda folder, force=False: f"rm -r {folder} force={force}", approver=s)
    def delete(folder, force=False):
        return folder

    delete("tmp")
    req = s.requests[0]
    assert req.tool == "delete"
    assert req.arguments == {"folder": "tmp", "force": False}
    assert req.preview == "rm -r tmp force=False"


def test_broken_preview_still_asks(scripted):
    s = scripted(True)

    def bad_preview(x):
        raise RuntimeError("disk on fire")

    @gate(risk="high", preview=bad_preview, approver=s)
    def act(x):
        return x

    assert act(1) == 1
    assert "preview failed: RuntimeError: disk on fire" in s.requests[0].preview


def test_terminal_prints_preview(monkeypatch, capsys):
    tty(monkeypatch, ["n"])

    @gate(risk="high", preview=lambda folder: f"3 files in {folder}\na.txt")
    def delete(folder):
        pass

    with pytest.raises(ApprovalDenied):
        delete("tmp")
    out = capsys.readouterr().out
    assert "[approval needed] delete  (high risk)" in out
    assert "| 3 files in tmp" in out
    assert "| a.txt" in out


def test_custom_name(scripted):
    s = scripted(True)

    @gate(risk="high", name="fs.delete", approver=s)
    def delete():
        pass

    delete()
    assert s.requests[0].tool == "fs.delete"
    assert audit_lines()[0]["tool"] == "fs.delete"


# ---- edit arguments ----------------------------------------------------


def test_edit_reruns_preview_and_asks_again(scripted):
    s = scripted(Decision(arguments={"folder": "tmp/old"}), True)

    @gate(risk="high", preview=lambda folder: f"deleting {folder}", approver=s)
    def delete(folder):
        return folder

    assert delete("/") == "tmp/old"
    assert s.requests[1].preview == "deleting tmp/old"
    assert s.requests[1].note == "arguments edited, please confirm"
    rec = audit_lines()[-1]
    assert rec["arguments"] == {"folder": "tmp/old"}
    assert rec["edited"] is True


def test_bad_edit_is_rejected_and_asks_again(scripted):
    s = scripted(Decision(arguments={"nope": 1}), False)

    @gate(risk="high", approver=s)
    def delete(folder):
        return folder

    with pytest.raises(ApprovalDenied):
        delete("tmp")
    assert s.requests[1].note.startswith("edit rejected")
    assert s.requests[1].arguments == {"folder": "tmp"}


def test_edit_on_terminal(monkeypatch):
    tty(monkeypatch, ["e", '{"folder": "safe"}', "y"])

    @gate(risk="high")
    def delete(folder):
        return folder

    assert delete("/") == "safe"


def test_edit_on_terminal_bad_json_then_cancel(monkeypatch, capsys):
    tty(monkeypatch, ["e", "{not json", "e", "[1]", "e", "", "n"])

    @gate(risk="high")
    def delete(folder):
        return folder

    with pytest.raises(ApprovalDenied):
        delete("/")
    out = capsys.readouterr().out
    assert "not valid JSON" in out
    assert "expected a JSON object" in out


def test_edit_keeps_redacted_value(scripted):
    s = scripted(Decision(arguments={"user": "bob", "password": "***"}), True)

    @gate(risk="high", redact=["password"], approver=s)
    def login(user, password):
        return user, password

    assert login("alice", "hunter2") == ("bob", "hunter2")


# ---- deny modes --------------------------------------------------------


def test_on_deny_return_gives_model_a_message(scripted):
    @gate(risk="high", on_deny="return", approver=scripted(False))
    def nuke():
        return "boom"

    msg = nuke()
    assert "denied" in msg and "nuke" in msg


def test_approval_denied_is_permission_error():
    assert issubclass(ApprovalDenied, PermissionError)


def test_approver_must_return_decision():
    @gate(risk="high", approver=lambda req: "sure")
    def nuke():
        pass

    with pytest.raises(TypeError):
        nuke()


def test_set_approver_is_used_by_default(scripted):
    s = scripted(True)
    set_approver(s)

    @gate(risk="high")
    def nuke():
        return "boom"

    assert nuke() == "boom"
    assert len(s.requests) == 1


def test_custom_approver_runs_without_terminal(monkeypatch, scripted):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    @gate(risk="high", approver=scripted(True))
    def nuke():
        return "boom"

    assert nuke() == "boom"


# ---- frameworks: async, signatures -------------------------------------


def test_async_tool(scripted):
    s = scripted(True)

    @gate(risk="high", preview=lambda n: f"n={n}", approver=s)
    async def fetch(n):
        await asyncio.sleep(0)
        return n * 2

    assert inspect.iscoroutinefunction(fetch)
    assert asyncio.run(fetch(21)) == 42
    assert s.requests[0].preview == "n=21"


def test_async_low_risk_and_denied(scripted):
    @gate(risk="low")
    async def read():
        return "data"

    @gate(risk="high", on_deny="return", approver=scripted(False))
    async def nuke():
        return "boom"

    assert asyncio.run(read()) == "data"
    assert "denied" in asyncio.run(nuke())


def test_signature_doc_and_annotations_survive():
    def original(path: str, *, force: bool = False) -> str:
        """Delete a path."""
        return path

    wrapped = gate(risk="high")(original)
    assert inspect.signature(wrapped) == inspect.signature(original)
    assert wrapped.__doc__ == "Delete a path."
    assert wrapped.__annotations__ == original.__annotations__
    assert wrapped.__wrapped__ is original


def test_wrong_arguments_raise_type_error_before_asking(scripted):
    s = scripted()

    @gate(risk="high", approver=s)
    def delete(folder):
        pass

    with pytest.raises(TypeError):
        delete()
    assert s.requests == []


def test_threads_share_one_always(scripted):
    answered = threading.Event()

    def slow_approver(req):
        answered.set()
        return Decision(approved=True, remember=True)

    calls = []
    counter = {"asks": 0}

    def counting(req):
        counter["asks"] += 1
        return slow_approver(req)

    @gate(risk="medium", approver=counting)
    def rename(i):
        calls.append(i)

    threads = [threading.Thread(target=rename, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(calls) == list(range(8))
    assert counter["asks"] == 1
