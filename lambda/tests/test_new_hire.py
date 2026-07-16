import os
import sys

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


def test_valid_payload_passes_validation_before_anything_else():
    result = new_hire.process_new_hire(dict(VALID_PAYLOAD))

    assert result.normalized_payload["employee_id"] == "E12345"
    assert result.unknown_fields == []


def test_invalid_payload_raises_and_is_not_swallowed():
    payload = dict(VALID_PAYLOAD)
    del payload["department"]

    with pytest.raises(ValidationError) as exc_info:
        new_hire.process_new_hire(payload)

    assert exc_info.value.field == "department"
