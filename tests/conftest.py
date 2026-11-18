import pytest

from agent_approval_gate import reset_session, set_approver
from agent_approval_gate.audit import AUDIT_ENV
from agent_approval_gate.policy import POLICY_ENV


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    """Each test runs in its own folder with no remembered decisions and the terminal approver."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(AUDIT_ENV, raising=False)
    monkeypatch.delenv(POLICY_ENV, raising=False)
    reset_session()
    set_approver(None)
    yield
    reset_session()
    set_approver(None)


class Scripted:
    """An approver that plays back answers and records every request it saw."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.answers.pop(0)


@pytest.fixture
def scripted():
    return Scripted
