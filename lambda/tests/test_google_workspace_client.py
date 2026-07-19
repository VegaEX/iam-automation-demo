import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from clients.google_workspace_client import GoogleWorkspaceClient  # noqa: E402


def test_delegate_inbox_returns_expected_structure():
    client = GoogleWorkspaceClient()

    result = client.delegate_inbox("departed@acme-corp.example", "manager@acme-corp.example")

    assert result == {
        "action": "delegate_inbox",
        "user_email": "departed@acme-corp.example",
        "delegate_email": "manager@acme-corp.example",
        "status": "DELEGATION_ACTIVE",
    }


def test_rename_account_returns_expected_structure():
    client = GoogleWorkspaceClient()

    result = client.rename_account("departed@acme-corp.example", "departed_deactivated")

    assert result == {
        "action": "rename_account",
        "user_email": "departed@acme-corp.example",
        "new_username": "departed_deactivated",
        "status": "RENAMED",
    }


def test_transfer_drive_returns_expected_structure():
    client = GoogleWorkspaceClient()

    result = client.transfer_drive("departed@acme-corp.example", "manager@acme-corp.example")

    assert result == {
        "action": "transfer_drive",
        "user_email": "departed@acme-corp.example",
        "new_owner_email": "manager@acme-corp.example",
        "status": "TRANSFER_QUEUED",
    }


def test_create_hidden_group_returns_expected_structure():
    client = GoogleWorkspaceClient()

    result = client.create_hidden_group("departed@acme-corp.example", "manager@acme-corp.example")

    assert result == {
        "action": "create_hidden_group",
        "group_email": "departed@acme-corp.example",
        "forwards_to": "manager@acme-corp.example",
        "status": "GROUP_CREATED",
    }


def test_schedule_deletion_returns_expected_structure_with_custom_days():
    client = GoogleWorkspaceClient()

    result = client.schedule_deletion("departed@acme-corp.example", days=45)

    assert result == {
        "action": "schedule_deletion",
        "user_email": "departed@acme-corp.example",
        "hold_days": 45,
        "status": "DELETION_SCHEDULED",
    }


def test_schedule_deletion_defaults_to_30_days():
    client = GoogleWorkspaceClient()

    result = client.schedule_deletion("departed@acme-corp.example")

    assert result["hold_days"] == 30
