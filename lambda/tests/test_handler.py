import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import handler  # noqa: E402


def _api_gateway_event(body_dict):
    return {"body": json.dumps(body_dict)}


def test_batch_over_25_records_raises_and_logs(caplog):
    caplog.set_level("ERROR")
    records = [{"event_type": "new_hire", "employee_id": f"E{i}"} for i in range(26)]
    event = _api_gateway_event({"records": records})

    with pytest.raises(handler.RunawayBatchError):
        handler.handler(event, None)

    assert any("runaway_batch_rejected" in r.message for r in caplog.records)


def test_batch_of_exactly_25_records_is_not_rejected():
    records = [{"event_type": "new_hire", "employee_id": f"E{i}"} for i in range(25)]
    event = _api_gateway_event({"records": records})

    with patch.object(handler.new_hire, "process_new_hire", return_value={"ok": True}) as mock_process:
        results = handler.handler(event, None)

        assert mock_process.call_count == 25
        assert results == [{"ok": True}] * 25


def test_single_new_hire_event_dispatches_to_new_hire_module():
    payload = {"event_type": "new_hire", "employee_id": "E1", "email": "ada@acme-corp.example"}
    event = _api_gateway_event(payload)

    with patch.object(handler.new_hire, "process_new_hire", return_value={"okta_user_id": "00u1"}) as mock_process:
        result = handler.handler(event, None)

        mock_process.assert_called_once_with(payload)
        assert result == {"okta_user_id": "00u1"}


def test_single_termination_event_dispatches_to_termination_module():
    payload = {"event_type": "termination", "email": "leaving@acme-corp.example"}
    event = _api_gateway_event(payload)

    with patch.object(
        handler.termination, "process_termination", return_value={"found": True}
    ) as mock_process:
        result = handler.handler(event, None)

        mock_process.assert_called_once_with(payload)
        assert result == {"found": True}


def test_unrecognized_event_type_raises():
    payload = {"event_type": "sabbatical", "employee_id": "E1"}
    event = _api_gateway_event(payload)

    with pytest.raises(ValueError):
        handler.handler(event, None)
