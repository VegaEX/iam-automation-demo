import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from issue_format import format_human_date, format_issue_body, format_slack_message  # noqa: E402


def test_format_issue_body_has_required_sections_without_deadline():
    body = format_issue_body(
        what_happened="Something happened.",
        what_needs_to_happen=["Do this.", "Then do that."],
        technical_details="- **Detail:** value",
    )

    assert "## What happened" in body
    assert "## What needs to happen" in body
    assert "## Technical details" in body
    assert "## Deadline" not in body
    assert "1. Do this." in body
    assert "2. Then do that." in body


def test_format_issue_body_includes_deadline_section_when_provided():
    body = format_issue_body(
        what_happened="Something happened.",
        what_needs_to_happen=["Do this."],
        technical_details="- **Detail:** value",
        deadline="Respond within 24 hours.",
    )

    assert "## Deadline" in body
    assert "Respond within 24 hours." in body


def test_format_slack_message_structure():
    message = format_slack_message(
        summary="Something happened.",
        action="Someone should do something.",
        issue_url="https://github.com/acme/repo/issues/1",
    )

    lines = message.split("\n")
    assert lines[0] == "*Something happened.*"
    assert lines[1] == "Someone should do something."
    assert lines[2] == "Details: https://github.com/acme/repo/issues/1"


def test_format_human_date_converts_iso_to_readable():
    assert format_human_date("2026-08-19") == "August 19, 2026"
