import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from provisioning import termination  # noqa: E402


def test_successful_termination_deactivates_and_removes_groups(caplog):
    caplog.set_level("INFO")
    payload = {"email": "leaving@acme-corp.example"}

    with patch.object(termination, "OktaClient") as mock_okta_cls:
        mock_okta = mock_okta_cls.return_value
        mock_okta.deactivate_user.return_value = "00u999"

        result = termination.process_termination(payload)

        mock_okta.deactivate_user.assert_called_once_with("leaving@acme-corp.example")
        mock_okta.remove_from_all_groups.assert_called_once_with("00u999")

        assert result == {
            "email": "leaving@acme-corp.example",
            "okta_user_id": "00u999",
            "found": True,
        }
        assert any("termination_processed" in r.message for r in caplog.records)


def test_termination_user_not_found_logs_warning_and_exits_cleanly(caplog):
    caplog.set_level("WARNING")
    payload = {"email": "ghost@acme-corp.example"}

    with patch.object(termination, "OktaClient") as mock_okta_cls:
        mock_okta = mock_okta_cls.return_value
        mock_okta.deactivate_user.return_value = None

        result = termination.process_termination(payload)

        mock_okta.remove_from_all_groups.assert_not_called()
        assert result == {"email": "ghost@acme-corp.example", "found": False}
        assert any("termination_user_not_found" in r.message for r in caplog.records)
