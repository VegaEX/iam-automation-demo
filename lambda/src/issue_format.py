from datetime import datetime


def format_issue_body(what_happened, what_needs_to_happen, technical_details, deadline=None):
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
    return "\n".join([f"*{summary}*", action, f"Details: {issue_url}"])


def format_human_date(iso_date_str):
    parsed = datetime.strptime(iso_date_str, "%Y-%m-%d")
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
