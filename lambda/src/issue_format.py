from datetime import datetime


def format_issue_body(what_happened, what_needs_to_happen, technical_details, deadline=None):
    """Build a GitHub issue body in this project's standard shape: a plain-
    English summary first, then concrete numbered actions, then full
    technical detail, with an optional deadline section only when there's
    an actual time-sensitive date attached.

    what_happened: str - one or two plain-English sentences, no jargon/IDs.
    what_needs_to_happen: list[str] - numbered automatically, written as
        instructions ("Do X"), not observations ("X was done").
    technical_details: str - pre-formatted Markdown (bullets, tables, code
        blocks) - all the resource IDs/timestamps/raw payloads live here.
    deadline: optional str - a plain statement of the actual date, only
        passed when something time-sensitive is genuinely attached.
    """
    numbered_actions = "\n".join(
        f"{i}. {action}" for i, action in enumerate(what_needs_to_happen, start=1)
    )

    sections = [
        "## What happened",
        "",
        what_happened.strip(),
        "",
        "## What needs to happen",
        "",
        numbered_actions,
        "",
        "## Technical details",
        "",
        technical_details.strip(),
    ]

    if deadline:
        sections += ["", "## Deadline", "", deadline.strip()]

    return "\n".join(sections)


def format_slack_message(summary, action, issue_url):
    """Build a Slack message in this project's standard 3-line shape: bold
    plain-English summary, what to do and who should do it, then a link to
    the GitHub issue for full detail."""
    return "\n".join([f"*{summary}*", action, f"Details: {issue_url}"])


def format_human_date(iso_date_str):
    """"2026-08-18" -> "August 18, 2026" - for deadline sections, where a
    plain-English date reads better than an ISO string."""
    parsed = datetime.strptime(iso_date_str, "%Y-%m-%d")
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
