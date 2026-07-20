import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from issue_format import format_human_date, format_issue_body, format_slack_message  # noqa: E402


def test_format_issue_body_has_all_sections_in_order():
    body = format_issue_body(
        what_happened="Something happened in plain English.",
        what_needs_to_happen=["Do this first.", "Then do this."],
        technical_details="- field: value",
        deadline="This will happen on August 18, 2026.",
    )

    assert body.index("## What happened") < body.index("## What needs to happen")
    assert body.index("## What needs to happen") < body.index("## Technical details")
    assert body.index("## Technical details") < body.index("## Deadline")
    assert "1. Do this first." in body
    assert "2. Then do this." in body
    assert "- field: value" in body
    assert "This will happen on August 18, 2026." in body


def test_format_issue_body_omits_deadline_section_when_not_given():
    body = format_issue_body(
        what_happened="Something happened.",
        what_needs_to_happen=["Do something."],
        technical_details="- field: value",
    )

    assert "## Deadline" not in body


def test_format_slack_message_has_three_lines_in_order():
    message = format_slack_message(
        summary="Something happened.",
        action="Someone should review it.",
        issue_url="https://github.com/acme/repo/issues/1",
    )

    lines = message.split("\n")
    assert lines[0] == "*Something happened.*"
    assert lines[1] == "Someone should review it."
    assert lines[2] == "Details: https://github.com/acme/repo/issues/1"


def test_format_human_date():
    assert format_human_date("2026-08-18") == "August 18, 2026"
    assert format_human_date("2026-01-05") == "January 5, 2026"
