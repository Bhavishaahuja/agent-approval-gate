import pytest

from agent_approval_gate import gate


def test_low_risk_runs_without_asking():
    @gate(risk="low")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_high_risk_denied_when_no_human(monkeypatch):
    # pytest has no real terminal, so this should be denied
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    @gate(risk="high")
    def nuke():
        return "boom"

    with pytest.raises(PermissionError):
        nuke()


def test_high_risk_runs_when_human_says_yes(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "y")

    @gate(risk="high", preview=lambda folder: f"deleting {folder}")
    def delete_files(folder):
        return f"deleted {folder}"

    assert delete_files("tmp") == "deleted tmp"


def test_bad_risk_level():
    with pytest.raises(ValueError):
        gate(risk="spicy")


def test_keeps_function_name():
    @gate(risk="low")
    def my_tool():
        pass

    assert my_tool.__name__ == "my_tool"
