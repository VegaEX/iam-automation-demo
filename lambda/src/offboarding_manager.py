import json
import logging
import os
from datetime import datetime, timedelta, timezone

from clients.github_client import GitHubClient
from clients.google_workspace_client import GoogleWorkspaceClient
from clients.secret_store import get_secret
from clients.slack_client import SlackClient
from clients.ssm_state_store import get_pending_removals, put_pending_removals
from issue_format import format_human_date, format_issue_body, format_slack_message

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "offboarding_config.json")
DEFAULT_HOLD_DAYS = 30

MANUAL_INSTRUCTIONS = {
    "github": "Remove {email} from the GitHub organization (Settings -> Members).",
    "salesforce": "Deactivate the Salesforce user license for {email} in Setup -> Users.",
    "atlassian": "Deactivate the Atlassian account for {email} in the Atlassian admin console.",
}


def _load_config(config_path=None):
    config_path = config_path or os.environ.get("OFFBOARDING_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    with open(config_path) as fh:
        return json.load(fh)


def resolve_hold_days(config=None):
    """The data-review/removal hold period, taken from whichever app in the
    config declares ownership_transfer: true (currently google_workspace).
    Falls back to DEFAULT_HOLD_DAYS if no app declares one, so the
    provisioning Lambda's Okta lockdown step and this module's checklist
    always agree on the same removal date."""
    config = config or _load_config()
    return next(
        (cfg["hold_days"] for cfg in config.values() if cfg.get("ownership_transfer") is True),
        DEFAULT_HOLD_DAYS,
    )


def _process_app(app_name, app_config, user_email, manager_email):
    """Dispatch a single app's configured termination behavior. Returns
    either a "manual" finding (for the GitHub checklist) or an "automatic"
    record of what was done."""
    if app_config["ownership_transfer"] == "manual_checklist":
        instructions = MANUAL_INSTRUCTIONS.get(
            app_name, f"Manually complete '{app_config['action']}' for {user_email}."
        ).format(email=user_email)
        return {
            "type": "manual",
            "app": app_name,
            "action": app_config["action"],
            "instructions": instructions,
        }

    if app_config["action"] == "deprovision_via_scim":
        note = (
            f"{app_name} is SCIM-provisioned from Okta group membership - removing the "
            "user from their Okta groups (already done) deprovisions this app automatically."
        )
        logger.info(json.dumps({"offboarding_scim_note": {"app": app_name, "note": note}}))
        return {"type": "automatic", "app": app_name, "note": note}

    if app_config["action"] == "delegate_to_manager":
        google = GoogleWorkspaceClient()
        hold_days = app_config.get("hold_days") or DEFAULT_HOLD_DAYS
        new_username = f"{user_email.split('@')[0]}_deactivated"

        results = [
            google.delegate_inbox(user_email, manager_email),
            google.rename_account(user_email, new_username),
            google.transfer_drive(user_email, manager_email),
            google.create_hidden_group(user_email, manager_email),
            google.schedule_deletion(user_email, days=hold_days),
        ]
        return {"type": "automatic", "app": app_name, "results": results}

    raise ValueError(f"no offboarding handler for app {app_name!r} action {app_config['action']!r}")


def run_offboarding(user_email, manager_email, employee_name=None, removal_date=None):
    """Read offboarding_config.json and execute the per-app termination
    sequence, record the pending removal, and open a manager checklist
    GitHub issue.

    Must only be called after Okta access has already been cut
    (OktaClient.initiate_offboarding) - this handles every *other* app plus
    the paper trail, not the security-critical Okta lockdown itself.
    """
    config = _load_config()

    automatic_actions = []
    manual_items = []

    for app_name, app_config in config.items():
        result = _process_app(app_name, app_config, user_email, manager_email)
        if result["type"] == "manual":
            manual_items.append(result)
        else:
            automatic_actions.append(result)

    if removal_date is None:
        hold_days = resolve_hold_days(config)
        removal_date = (datetime.now(timezone.utc) + timedelta(days=hold_days)).date().isoformat()

    issue = _open_checklist_issue(
        employee_name or user_email,
        user_email,
        manager_email,
        automatic_actions,
        manual_items,
        removal_date,
    )

    _record_pending_removal(user_email, manager_email, removal_date, issue.get("number"))

    return {
        "automatic_actions": automatic_actions,
        "manual_items": manual_items,
        "removal_date": removal_date,
        "github_issue": issue,
    }


def _format_automatic_action(action):
    if "note" in action:
        return f"- **{action['app']}**: {action['note']}"
    statuses = ", ".join(r["status"] for r in action["results"])
    return f"- **{action['app']}**: {statuses}"


def _format_technical_details(automatic_actions, manual_items):
    lines = [
        "### Automatic actions taken",
        "- Okta account deactivated, sessions cleared, renamed, and moved to `pending_removal`",
    ]
    lines += [_format_automatic_action(action) for action in automatic_actions]
    lines.append("")

    if manual_items:
        lines += [
            "### Manual items requiring manager attention",
            "",
            "| App | Action Needed | Instructions |",
            "|---|---|---|",
        ]
        lines += [
            f"| {item['app']} | {item['action']} | {item['instructions']} |" for item in manual_items
        ]

    return "\n".join(lines)


def _format_what_needs_to_happen(manual_items):
    actions = ["Review the automatic actions completed below to confirm they succeeded."]
    if manual_items:
        actions.append("Complete each manual item listed below by hand.")
    actions.append("Reassign or back up any remaining data owned by this person before the deadline below.")
    actions.append("Close this issue once everything above is done.")
    return actions


def _format_issue_body(employee_name, user_email, manager_email, automatic_actions, manual_items, removal_date):
    human_date = format_human_date(removal_date)
    return format_issue_body(
        what_happened=(
            f"{employee_name} ({user_email}) has left the company - their manager "
            f"is {manager_email}. Immediate Okta access has already been removed "
            "automatically, but some other accounts need manual follow-up."
        ),
        what_needs_to_happen=_format_what_needs_to_happen(manual_items),
        technical_details=_format_technical_details(automatic_actions, manual_items),
        deadline=(
            f"Review and reassign any remaining data owned by {user_email} before "
            f"{human_date}. The Okta account will be permanently deleted on "
            f"{human_date} by the scheduled removal Lambda, if not addressed sooner."
        ),
    )


def _open_checklist_issue(employee_name, user_email, manager_email, automatic_actions, manual_items, removal_date):
    github = GitHubClient(
        token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
        repo=os.environ["GITHUB_REPO"],
    )
    issue = github.create_issue(
        title=f"Offboarding checklist — {employee_name}",
        body=_format_issue_body(
            employee_name, user_email, manager_email, automatic_actions, manual_items, removal_date
        ),
    )
    logger.info(
        json.dumps(
            {
                "offboarding_checklist_opened": {
                    "employee": employee_name,
                    "email": user_email,
                    "issue_number": issue.get("number"),
                }
            }
        )
    )

    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_PARAM_NAME"]))
    if manual_items:
        action = (
            f"Manual steps needed for: {', '.join(item['app'] for item in manual_items)} - "
            "review the checklist issue."
        )
    else:
        action = "No manual steps needed - review the automatic actions taken."
    slack.post_alert(
        channel=os.environ.get("SLACK_ALERTS_CHANNEL", "#iam-alerts"),
        message=format_slack_message(
            summary=f"{employee_name} has left - immediate Okta access removed.",
            action=action,
            issue_url=issue["html_url"],
        ),
        severity="warning",
    )

    return issue


def _record_pending_removal(user_email, manager_email, removal_date, github_issue_number):
    param_name = os.environ["PENDING_REMOVALS_PARAM_NAME"]
    records = get_pending_removals(param_name)
    records.append(
        {
            "email": user_email,
            "manager_email": manager_email,
            "removal_date": removal_date,
            "github_issue_number": github_issue_number,
        }
    )
    put_pending_removals(param_name, records)
