from agent_approval_gate.cli import main


def test_demo_with_human(monkeypatch, capsys):
    answers = iter(["a", "y"])  # always for rename, yes for delete
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))

    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "renamed draft.txt -> hello.txt" in out
    assert "about to delete 3 file(s)" in out
    assert "deleted cache/" in out
    assert "rename_file   medium  allowed  session" in out


def test_demo_without_human_denies_safely(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "delete_files  high    denied   no_human" in out
    assert "no human was available to approve it" in out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "demo" in capsys.readouterr().out
