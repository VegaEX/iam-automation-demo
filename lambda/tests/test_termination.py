import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import offboarding_manager  # noqa: E402
from provisioning import termination  # noqa: E402


def test_termination_end_to_end_deactivates_renames_and_opens_checklist(caplog):
    caplog.set_level("INFO")
    payload = {
        "email": "leaving@acme-corp.example",
        "manager_email": "manager@acme-corp.example",
        "employee_name": "Jamie Doe",
    }

    with patch.object(termination, "OktaClient") as mock_okta_cls, patch.object(
        offboarding_manager, "resolve_hold_days", return_value=30
    ), patch.object(offboarding_manager, "run_offboarding") as mock_run_offboarding:
        mock_okta = mock_okta_cls.return_value
        mock_okta.initiate_offboarding.return_value = {
            "user_id": "00u1",
            "original_login": "leaving@acme-corp.example",
            "new_login": "leaving@acme-corp.example_deactivated",
            "removal_date": "2026-08-16",
        }
        mock_run_offboarding.return_value = {
            "automatic_actions": [{"type": "automatic", "app": "slack", "note": "scim note"}],
            "manual_items": [
                {
                    "type": "manual",
                    "app": "github",
                    "action": "remove_org_membership",
                    "instructions": "remove them",
                }
            ],
            "removal_date": "2026-08-16",
            "github_issue": {"number": 55},
        }

        result = termination.process_termination(payload)

        # Okta lockdown happens first, and with the hold_days resolved from
        # offboarding_config.json - not some independently-guessed default.
        mock_okta.initiate_offboarding.assert_called_once_with(
            "leaving@acme-corp.example", "manager@acme-corp.example", hold_days=30
        )
        # The per-app/checklist step only runs after that, reusing the same
        # removal_date Okta's lockdown already committed to.
        mock_run_offboarding.assert_called_once_with(
            user_email="leaving@acme-corp.example",
            manager_email="manager@acme-corp.example",
            employee_name="Jamie Doe",
            removal_date="2026-08-16",
        )

        assert result == {
            "email": "leaving@acme-corp.example",
            "okta_user_id": "00u1",
            "found": True,
            "removal_date": "2026-08-16",
            "manual_items_count": 1,
        }
        assert any("termination_processed" in r.message for r in caplog.records)


def test_termination_user_not_found_logs_warning_and_exits_cleanly(caplog):
    caplog.set_level("WARNING")
    payload = {"email": "ghost@acme-corp.example"}

    with patch.object(termination, "OktaClient") as mock_okta_cls, patch.object(
        offboarding_manager, "resolve_hold_days", return_value=30
    ), patch.object(offboarding_manager, "run_offboarding") as mock_run_offboarding:
        mock_okta = mock_okta_cls.return_value
        mock_okta.initiate_offboarding.return_value = None

        result = termination.process_termination(payload)

        mock_run_offboarding.assert_not_called()
        assert result == {"email": "ghost@acme-corp.example", "found": False}
        assert any("termination_user_not_found" in r.message for r in caplog.records)
