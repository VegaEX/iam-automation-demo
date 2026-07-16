import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from classifier import classify_event  # noqa: E402


def test_known_automation_actor_is_approved(monkeypatch):
    monkeypatch.setenv("KNOWN_AUTOMATION_ACTOR_IDS", "00t1provisioninglambda,00t1terraformci")
    event = {"actor": {"id": "00t1terraformci", "type": "SSWS"}}

    assert classify_event(event) == "approved_automation"


def test_system_actor_is_hr_driven_pattern(monkeypatch):
    monkeypatch.delenv("KNOWN_AUTOMATION_ACTOR_IDS", raising=False)
    event = {"actor": {"id": "okta-internal-engine", "type": "System"}}

    assert classify_event(event) == "approved_hr_pattern"


def test_unrecognized_human_actor_requires_review(monkeypatch):
    monkeypatch.delenv("KNOWN_AUTOMATION_ACTOR_IDS", raising=False)
    event = {"actor": {"id": "00u1someitadmin", "type": "User"}}

    assert classify_event(event) == "manual_review_required"


def test_missing_actor_requires_review(monkeypatch):
    monkeypatch.delenv("KNOWN_AUTOMATION_ACTOR_IDS", raising=False)

    assert classify_event({}) == "manual_review_required"
