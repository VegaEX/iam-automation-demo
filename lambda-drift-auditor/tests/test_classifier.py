import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from classifier import (  # noqa: E402
    classify_admin_privilege_event,
    classify_event,
    is_admin_privilege_event,
)


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


def test_is_admin_privilege_event_true_for_grant_with_role_target():
    event = {
        "eventType": "user.account.privilege.grant",
        "target": [{"type": "AdminRoleTarget", "displayName": "Super Administrator"}],
    }

    assert is_admin_privilege_event(event) is True


def test_is_admin_privilege_event_false_for_wrong_event_type():
    event = {
        "eventType": "group.user_membership.add",
        "target": [{"type": "AdminRoleTarget", "displayName": "Super Administrator"}],
    }

    assert is_admin_privilege_event(event) is False


def test_is_admin_privilege_event_false_when_no_role_shaped_target():
    event = {
        "eventType": "user.account.privilege.grant",
        "target": [{"type": "User", "displayName": "Jane Admin"}],
    }

    assert is_admin_privilege_event(event) is False


def test_classify_admin_privilege_event_known_automation(monkeypatch):
    monkeypatch.setenv("KNOWN_AUTOMATION_ACTOR_IDS", "00t1terraformci")
    event = {"actor": {"id": "00t1terraformci", "type": "SSWS"}}

    assert classify_admin_privilege_event(event) == "admin_grant_known_automation"


def test_classify_admin_privilege_event_unknown_actor(monkeypatch):
    monkeypatch.delenv("KNOWN_AUTOMATION_ACTOR_IDS", raising=False)
    event = {"actor": {"id": "00u1someitadmin", "type": "User"}}

    assert classify_admin_privilege_event(event) == "admin_grant_unknown_actor"
