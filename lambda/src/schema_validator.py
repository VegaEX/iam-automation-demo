import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from clients.github_client import GitHubClient
from clients.secret_store import get_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "adp_schema.json")

# Dash replacement (below) only applies to actual person-name fields - a
# department or job title legitimately containing an en/em dash shouldn't
# have it silently rewritten.
NAME_FIELDS = {"first_name", "last_name"}

# The local-part character class here is deliberately ASCII-only, which is
# what rejects non-ASCII characters before the "@" - there's no separate
# non-ASCII check because the regex simply won't match if one is present.
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

DATE_INPUT_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y")

_SMART_QUOTE_MAP = {
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
}

_DASH_MAP = {
    "–": "-",  # en dash
    "—": "-",  # em dash
}

NON_BREAKING_SPACE = " "


class ValidationError(Exception):
    """A structured validation failure - which field, and why."""

    def __init__(self, field, reason):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


@dataclass
class ValidationResult:
    normalized_payload: dict
    normalizations: list = field(default_factory=list)
    unknown_fields: list = field(default_factory=list)


class SchemaValidator:
    """Validates and normalizes an ADP new-hire payload against adp_schema.json."""

    def __init__(self, schema_path=None):
        schema_path = schema_path or os.environ.get("ADP_SCHEMA_PATH", DEFAULT_SCHEMA_PATH)
        with open(schema_path) as fh:
            self.schema = json.load(fh)

    def validate_and_normalize(self, payload):
        self._check_required_fields(payload)

        normalized = {}
        normalizations = []

        for field_name, field_def in self.schema.items():
            value = payload[field_name] if field_name in payload else field_def.get("default")
            value = self._check_type(field_name, field_def, value)

            if isinstance(value, str):
                value, string_normalizations = self._normalize_string(field_name, value)
                normalizations.extend(string_normalizations)

            if field_def["type"] == "email" and value:
                self._validate_email(field_name, value)

            if field_def["type"] == "date" and value:
                value, date_normalizations = self._normalize_date(field_name, value)
                normalizations.extend(date_normalizations)

            normalized[field_name] = value

        unknown_fields = sorted(set(payload) - set(self.schema))

        for normalization in normalizations:
            logger.info(json.dumps({"payload_normalization": normalization}))

        if unknown_fields:
            for unknown_field in unknown_fields:
                logger.info(
                    json.dumps(
                        {
                            "unknown_adp_field": {
                                "field": unknown_field,
                                "employee_id": payload.get("employee_id"),
                            }
                        }
                    )
                )
            self._report_unknown_fields(payload, unknown_fields)

        return ValidationResult(
            normalized_payload=normalized,
            normalizations=normalizations,
            unknown_fields=unknown_fields,
        )

    def _check_required_fields(self, payload):
        for field_name, field_def in self.schema.items():
            if not field_def["required"]:
                continue
            value = payload.get(field_name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                raise ValidationError(field_name, "required field missing")

    def _check_type(self, field_name, field_def, value):
        if value is None:
            return value

        # Every type this schema declares ("string", "email", "date") arrives
        # as a plain JSON string - email/date get their own format-specific
        # checks further down, this just guards against e.g. a number or
        # object showing up where a string was expected.
        if not isinstance(value, str):
            raise ValidationError(field_name, f"expected string, got {type(value).__name__}")
        return value

    def _normalize_string(self, field_name, value):
        original = value

        result = value.strip()
        result = unicodedata.normalize("NFC", result)
        result = result.replace(NON_BREAKING_SPACE, " ")

        for smart, straight in _SMART_QUOTE_MAP.items():
            result = result.replace(smart, straight)

        if field_name in NAME_FIELDS:
            for dash, hyphen in _DASH_MAP.items():
                result = result.replace(dash, hyphen)

        normalizations = []
        if result != original:
            normalizations.append(
                {"field": field_name, "original": original, "normalized": result}
            )
        return result, normalizations

    def _validate_email(self, field_name, value):
        if not EMAIL_PATTERN.match(value):
            raise ValidationError(field_name, f"invalid email format: {value!r}")

    def _normalize_date(self, field_name, value):
        for fmt in DATE_INPUT_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            normalized = parsed.strftime("%Y-%m-%d")
            normalizations = []
            if normalized != value:
                normalizations.append(
                    {"field": field_name, "original": value, "normalized": normalized}
                )
            return normalized, normalizations

        raise ValidationError(field_name, f"unrecognized date format: {value!r}")

    def _report_unknown_fields(self, payload, unknown_fields):
        body_lines = [
            "The ADP new-hire payload below contained fields this schema doesn't recognize.",
            "",
            f"- **Employee ID:** {payload.get('employee_id', '(unknown)')}",
            "- **Unmapped fields:**",
        ]
        for name in unknown_fields:
            sample_value = str(payload[name])[:50]
            body_lines.append(f"  - `{name}`: `{sample_value}`")
        body_lines += [
            "",
            "Add these to `lambda/src/adp_schema.json` (with an Okta attribute "
            "mapping) if they're meaningful, or confirm they can be safely ignored.",
        ]

        github = GitHubClient(
            token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
            repo=os.environ["GITHUB_REPO"],
        )
        github.create_issue(
            title="ADP payload contains unmapped fields — schema review required",
            body="\n".join(body_lines),
        )
