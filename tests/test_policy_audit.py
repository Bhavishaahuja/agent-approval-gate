import json
from pathlib import Path

import pytest

from agent_approval_gate import ApprovalDenied, gate
from agent_approval_gate.audit import AUDIT_ENV, clean
from agent_approval_gate.policy import POLICY_ENV, parse


def audit_lines(path="approval_audit.jsonl"):
    p = Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


# ---- policy file -------------------------------------------------------


def test_policy_overrides_code_tier(scripted):
    Path("approval.toml").write_text('[tools]\nread_db = "high"\n')
    s = scripted(True)

    @gate(risk="low", approver=s)
    def read_db():
        return "rows"

    assert read_db() == "rows"
    assert s.requests[0].risk == "high"


def test_policy_can_relax_with_wildcard(scripted):
    Path("approval.toml").write_text('[tools]\n"list_*" = "low"\n')
    s = scripted()

    @gate(risk="high", approver=s)
    def list_buckets():
        return ["a"]

    assert list_buckets() == ["a"]
    assert s.requests == []


def test_exact_name_beats_pattern(scripted):
    Path("approval.toml").write_text('[tools]\n"drop_*" = "low"\ndrop_prod = "high"\n')
    s = scripted(False)

    @gate(risk="medium", approver=s)
    def drop_prod():
        pass

    with pytest.raises(ApprovalDenied):
        drop_prod()


def test_policy_reloads_when_file_changes(scripted, tmp_path):
    import os

    policy_file = Path("approval.toml")
    policy_file.write_text('[tools]\nact = "low"\n')
    s = scripted(False)

    @gate(risk="high", approver=s)
    def act():
        return "ok"

    assert act() == "ok"
    policy_file.write_text('[tools]\nact = "high"\n')
    st = policy_file.stat()
    os.utime(policy_file, (st.st_atime, st.st_mtime + 5))
    with pytest.raises(ApprovalDenied):
        act()


def test_non_interactive_allow(monkeypatch):
    Path("approval.toml").write_text('[defaults]\nnon_interactive = "allow"\n')
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    @gate(risk="high")
    def deploy():
        return "shipped"

    assert deploy() == "shipped"
    rec = audit_lines()[-1]
    assert (rec["decision"], rec["reason"]) == ("allowed", "no_human")


def test_policy_env_path(monkeypatch, tmp_path, scripted):
    custom = tmp_path / "elsewhere.toml"
    custom.write_text('[tools]\nact = "low"\n')
    monkeypatch.setenv(POLICY_ENV, str(custom))
    s = scripted()

    @gate(risk="high", approver=s)
    def act():
        return 1

    assert act() == 1


def test_missing_policy_env_file_is_an_error(monkeypatch):
    monkeypatch.setenv(POLICY_ENV, "/no/such/approval.toml")

    @gate(risk="low")
    def act():
        return 1

    with pytest.raises(FileNotFoundError):
        act()


@pytest.mark.parametrize(
    "text",
    [
        '[tools]\nact = "spicy"\n',
        '[defaults]\nnon_interactive = "maybe"\n',
        '[defaults]\ntypo = 1\n',
        '[toolz]\n',
        '[defaults]\naudit_log = 3\n',
        "not = [valid toml",
    ],
)
def test_bad_policy_is_rejected(text):
    with pytest.raises(ValueError):
        parse(text)


def test_policy_can_disable_audit_log(scripted):
    Path("approval.toml").write_text("[defaults]\naudit_log = false\n")

    @gate(risk="low")
    def act():
        return 1

    act()
    assert not Path("approval_audit.jsonl").exists()


def test_policy_custom_audit_path():
    Path("approval.toml").write_text('[defaults]\naudit_log = "logs.jsonl"\n')

    @gate(risk="low")
    def act():
        return 1

    act()
    assert audit_lines("logs.jsonl")[0]["tool"] == "act"


# ---- audit log ---------------------------------------------------------


def test_every_decision_is_logged(scripted):
    s = scripted(True, False)

    @gate(risk="low")
    def read(path):
        return path

    @gate(risk="high", approver=s)
    def delete(path):
        return path

    read("a")
    delete("b")
    with pytest.raises(ApprovalDenied):
        delete("c")

    recs = audit_lines()
    assert [(r["tool"], r["decision"], r["reason"]) for r in recs] == [
        ("read", "allowed", "low_risk"),
        ("delete", "allowed", "human"),
        ("delete", "denied", "human"),
    ]
    assert recs[1]["arguments"] == {"path": "b"}
    assert recs[1]["risk"] == "high"
    assert "ts" in recs[0]


def test_redacted_fields_never_hit_disk_or_prompt(scripted):
    s = scripted(True)

    @gate(risk="high", redact=["api_key"], approver=s)
    def call(url, api_key, opts=None):
        return url

    call("https://x", "sk-secret", opts={"api_key": "sk-nested"})
    raw = Path("approval_audit.jsonl").read_text()
    assert "sk-secret" not in raw
    assert "sk-nested" not in raw
    assert s.requests[0].arguments["api_key"] == "***"


def test_audit_env_overrides_and_disables(monkeypatch):
    monkeypatch.setenv(AUDIT_ENV, "custom.jsonl")

    @gate(risk="low")
    def act():
        return 1

    act()
    assert len(audit_lines("custom.jsonl")) == 1

    monkeypatch.setenv(AUDIT_ENV, "off")
    act()
    assert len(audit_lines("custom.jsonl")) == 1
    assert not Path("approval_audit.jsonl").exists()


def test_unwritable_audit_log_warns_but_runs(monkeypatch, tmp_path):
    monkeypatch.setenv(AUDIT_ENV, str(tmp_path / "missing-dir" / "log.jsonl"))

    @gate(risk="low")
    def act():
        return 1

    with pytest.warns(UserWarning, match="could not write audit log"):
        assert act() == 1


def test_clean_shortens_and_handles_odd_values():
    out = clean({"s": "x" * 500, "l": list(range(50)), "o": object(), "n": None})
    assert len(out["s"]) == 200 and out["s"].endswith("...")
    assert len(out["l"]) == 21 and out["l"][-1] == "... 30 more"
    assert out["o"].startswith("<object object")
    assert out["n"] is None
