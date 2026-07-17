import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from provisioning import new_hire  # noqa: E402
from schema_validator import ValidationError  # noqa: E402

VALID_PAYLOAD = {
    "employee_id": "E12345",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada.lovelace@acme-corp.example",
    "department": "Engineering",
    "start_date": "2026-08-01",
    "employment_type": "full_time",
}


def test_successful_new_hire_creates_user_and_assigns_groups(caplog):
    caplog.set_level("INFO")

    with patch.object(new_hire, "OktaClient") as mock_okta_cls:
        mock_okta = mock_okta_cls.return_value
        mock_okta.create_user.return_value = "00u123"

        result = new_hire.process_new_hire(dict(VALID_PAYLOAD))

        mock_okta.create_user.assert_called_once()
        created_from = mock_okta.create_user.call_args[0][0]
        assert created_from["employee_id"] == "E12345"

        mock_okta.activate_user.assert_called_once_with("00u123")
        mock_okta.assign_to_groups.assert_called_once_with("00u123", "Engineering")

        assert result["okta_user_id"] == "00u123"
        assert any("new_hire_provisioned" in r.message for r in caplog.records)


def test_invalid_payload_raises_before_touching_okta():
    payload = dict(VALID_PAYLOAD)
    del payload["department"]

    with patch.object(new_hire, "OktaClient") as mock_okta_cls:
        with pytest.raises(ValidationError) as exc_info:
            new_hire.process_new_hire(payload)

        assert exc_info.value.field == "department"
        mock_okta_cls.assert_not_called()
