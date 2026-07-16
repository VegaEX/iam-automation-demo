import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import schema_validator  # noqa: E402
from schema_validator import SchemaValidator, ValidationError  # noqa: E402

VALID_PAYLOAD = {
    "employee_id": "E12345",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada.lovelace@acme-corp.example",
    "department": "Engineering",
    "start_date": "2026-08-01",
    "employment_type": "full_time",
}


def test_valid_payload_normalizes_cleanly():
    validator = SchemaValidator()

    result = validator.validate_and_normalize(dict(VALID_PAYLOAD))

    assert result.unknown_fields == []
    assert result.normalized_payload["employee_id"] == "E12345"
    assert result.normalized_payload["email"] == "ada.lovelace@acme-corp.example"
    # Optional fields not present in the payload get their schema default.
    assert result.normalized_payload["title"] == ""
    assert result.normalized_payload["manager_email"] is None


def test_missing_required_field_raises_with_field_name():
    payload = dict(VALID_PAYLOAD)
    del payload["email"]

    validator = SchemaValidator()
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_and_normalize(payload)

    assert exc_info.value.field == "email"
    assert exc_info.value.reason == "required field missing"


def test_unknown_field_is_collected_not_raised_and_reported(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-automation-demo/github/token")
    monkeypatch.setenv("GITHUB_REPO", "acme-corp/iam-automation-demo")

    payload = dict(VALID_PAYLOAD)
    payload["favorite_snack"] = "pretzels"

    with patch.object(schema_validator, "GitHubClient") as mock_gh_cls, patch.object(
        schema_validator, "get_secret", return_value="dummy-secret"
    ):
        mock_gh = mock_gh_cls.return_value
        validator = SchemaValidator()
        result = validator.validate_and_normalize(payload)

        assert result.unknown_fields == ["favorite_snack"]
        mock_gh.create_issue.assert_called_once()
        _, kwargs = mock_gh.create_issue.call_args
        assert kwargs["title"] == "ADP payload contains unmapped fields — schema review required"
        assert "favorite_snack" in kwargs["body"]
        assert "pretzels" in kwargs["body"]
        assert "E12345" in kwargs["body"]


def test_em_dash_in_name_field_normalizes_to_hyphen():
    payload = dict(VALID_PAYLOAD)
    payload["last_name"] = "Smith—Jones"  # em dash

    validator = SchemaValidator()
    result = validator.validate_and_normalize(payload)

    assert result.normalized_payload["last_name"] == "Smith-Jones"
    assert any(n["field"] == "last_name" for n in result.normalizations)


def test_non_ascii_email_fails_validation():
    payload = dict(VALID_PAYLOAD)
    payload["email"] = "adaü@acme-corp.example"

    validator = SchemaValidator()
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_and_normalize(payload)

    assert exc_info.value.field == "email"


def test_mmddyyyy_date_normalizes_to_iso8601():
    payload = dict(VALID_PAYLOAD)
    payload["start_date"] = "08/01/2026"

    validator = SchemaValidator()
    result = validator.validate_and_normalize(payload)

    assert result.normalized_payload["start_date"] == "2026-08-01"
    assert any(n["field"] == "start_date" for n in result.normalizations)


def test_mmddyyyy_with_dashes_also_normalizes():
    payload = dict(VALID_PAYLOAD)
    payload["start_date"] = "08-01-2026"

    validator = SchemaValidator()
    result = validator.validate_and_normalize(payload)

    assert result.normalized_payload["start_date"] == "2026-08-01"


def test_non_breaking_space_in_name_normalizes_to_regular_space():
    payload = dict(VALID_PAYLOAD)
    payload["first_name"] = "Mary Jane"  # non-breaking space

    validator = SchemaValidator()
    result = validator.validate_and_normalize(payload)

    assert result.normalized_payload["first_name"] == "Mary Jane"
    assert any(n["field"] == "first_name" for n in result.normalizations)
