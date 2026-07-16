import json
import logging
import os
from datetime import datetime, timedelta, timezone

<<<<<<< HEAD
from classifier import (
    classify_admin_privilege_event,
    classify_event,
    find_admin_role_target,
    is_admin_privilege_event,
)
from github_client import GitHubClient
from issue_format import format_issue_body, format_slack_message
from managed_resources import load_managed_resource_ids
from okta_log_client import OktaLogClient
from okta_role_client import get_holder_email, list_admin_role_holders
from secret_store import get_secret
from slack_client import SlackClient
from ssm_state_store import get_json_list, get_open_escalations, put_json_list, put_open_escalations

# An escalation still open after this long gets a repeated Slack nag every
# time check_unacknowledged_escalations runs (every 6 hours - see
# terraform/modules/okta_drift_auditor), until someone closes the issue.
ESCALATION_REMINDER_HOURS = 24
=======
from classifier import classify_event
from github_client import GitHubClient
from managed_resources import load_managed_resource_ids
from okta_log_client import OktaLogClient
from secret_store import get_secret
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Okta System Log eventTypes that touch group, policy, or app-assignment
# state - the categories this project's Terraform config manages. Anything
# else (logins, password resets, etc.) is out of scope for this auditor.
RELEVANT_EVENT_TYPES = {
    "group.lifecycle.create",
    "group.lifecycle.delete",
    "group.profile.update",
    "group.user_membership.add",
    "group.user_membership.remove",
    "policy.lifecycle.create",
    "policy.lifecycle.update",
    "policy.lifecycle.delete",
    "policy.rule.update",
    "application.lifecycle.update",
    "application.group_membership.add",
    "application.group_membership.remove",
    "application.user_membership.add",
    "application.user_membership.remove",
}


def handler(event, context):
    lookback_minutes = int(os.environ.get("LOOKBACK_MINUTES", "15"))
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

    okta_logs = OktaLogClient(
        org_url=f"https://{os.environ['OKTA_ORG_NAME']}.{os.environ['OKTA_BASE_URL']}",
        api_token=get_secret(os.environ["OKTA_API_TOKEN_PARAM_NAME"]),
    )
    github = GitHubClient(
        token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
        repo=os.environ["GITHUB_REPO"],
    )
<<<<<<< HEAD
    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_PARAM_NAME"]))
    slack_channel = os.environ.get("SLACK_ALERTS_CHANNEL", "#iam-alerts")
=======
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
    managed_ids = load_managed_resource_ids()

    all_events = okta_logs.get_events_since(since)
    relevant_events = [e for e in all_events if e.get("eventType") in RELEVANT_EVENT_TYPES]
<<<<<<< HEAD
    admin_privilege_events = [e for e in all_events if is_admin_privilege_event(e)]

    results = {
        "approved": 0,
        "escalated": 0,
        "ignored": 0,
        "admin_grants_approved": 0,
        "admin_grants_escalated": 0,
        "unexpected_admin_holders": 0,
    }
=======

    results = {"approved": 0, "escalated": 0, "ignored": 0}
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

    for log_event in relevant_events:
        target_ids = {t.get("id") for t in log_event.get("target", []) if t.get("id")}

        # If we have a managed-resource list and none of this event's targets
        # are on it, it's touching something Terraform doesn't own - not our
        # concern.
        if managed_ids and not (target_ids & managed_ids):
            results["ignored"] += 1
            continue

        classification = classify_event(log_event)
        actor = log_event.get("actor", {}) or {}

        log_entry = {
            "event_type": log_event.get("eventType"),
            "event_time": log_event.get("published"),
            "actor": actor.get("displayName") or actor.get("alternateId"),
            "actor_type": actor.get("type"),
            "targets": [t.get("displayName") or t.get("id") for t in log_event.get("target", [])],
            "classification": classification,
        }
        logger.info(json.dumps({"drift_audit": log_entry}))

        if classification in ("approved_automation", "approved_hr_pattern"):
            results["approved"] += 1
            continue

        results["escalated"] += 1
<<<<<<< HEAD
        issue = github.create_issue(
            title="Manual Okta change detected — review required",
            body=_format_issue_body(log_event, log_entry),
        )
        _record_open_escalation(issue)
        slack.post_alert(
            channel=slack_channel,
            message=format_slack_message(
                summary=(
                    "A change was made directly in Okta outside the normal "
                    "automated process."
                ),
                action=(
                    f"Review needed: {log_entry['actor']} changed "
                    f"{', '.join(log_entry['targets'])} - approve or revert it via the issue."
                ),
                issue_url=issue["html_url"],
            ),
            severity="warning",
        )

    # Admin role grants get their own detection path, not filtered by
    # managed_ids - the whole point is catching grants Terraform's
    # okta_admin_roles module doesn't know about too, not just drift on ones
    # it does.
    for log_event in admin_privilege_events:
        actor = log_event.get("actor", {}) or {}
        classification = classify_admin_privilege_event(log_event)

        log_entry = {
            "event_type": log_event.get("eventType"),
            "event_time": log_event.get("published"),
            "actor": actor.get("displayName") or actor.get("alternateId"),
            "actor_type": actor.get("type"),
            "classification": classification,
        }
        logger.info(json.dumps({"admin_privilege_audit": log_entry}))

        if classification == "admin_grant_known_automation":
            results["admin_grants_approved"] += 1
            continue

        results["admin_grants_escalated"] += 1
        issue = github.create_issue(
            title="Administrator access granted — immediate review required",
            body=_format_admin_grant_issue_body(log_event, log_entry),
        )
        _record_open_escalation(issue)
        slack.post_alert(
            channel=slack_channel,
            message=format_slack_message(
                summary=(
                    "Administrator access was granted outside the normal "
                    "approval process."
                ),
                action=(
                    f"Urgent review needed: {log_entry['actor']} granted admin "
                    "access - respond within 24 hours."
                ),
                issue_url=issue["html_url"],
            ),
            severity="critical",
        )

    # Catches admin roles that were granted before this auditor was ever
    # running (or before KNOWN_AUTOMATION_ACTOR_IDS/KNOWN_ADMIN_EMAILS were
    # populated) - a state check, not an event check, same distinction as
    # access_review.py vs the rest of this Lambda.
    results["unexpected_admin_holders"] = _check_unexpected_admin_holders(
        okta_org_url=f"https://{os.environ['OKTA_ORG_NAME']}.{os.environ['OKTA_BASE_URL']}",
        okta_api_token=okta_logs.api_token,
        github=github,
        slack=slack,
        slack_channel=slack_channel,
    )
=======
        github.create_issue(
            title="Manual Okta change detected — review required",
            body=_format_issue_body(log_event, log_entry),
        )
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

    logger.info(json.dumps({"drift_audit_summary": results}))
    return results


<<<<<<< HEAD
def _check_unexpected_admin_holders(okta_org_url, okta_api_token, github, slack, slack_channel):
    known_emails = {
        e.strip().lower() for e in os.environ.get("KNOWN_ADMIN_EMAILS", "").split(",") if e.strip()
    }
    reported_param_name = os.environ["REPORTED_ADMIN_ALERTS_PARAM_NAME"]
    already_reported = set(get_json_list(reported_param_name))

    holders = list_admin_role_holders(okta_org_url, okta_api_token)
    newly_reported = []

    for holder in holders:
        email = get_holder_email(holder)
        if not email:
            continue

        email_lower = email.lower()
        if email_lower in known_emails or email_lower in already_reported:
            continue

        logger.info(json.dumps({"unexpected_admin_holder": {"email": email}}))

        issue = github.create_issue(
            title="Administrator access granted — immediate review required",
            body=_format_unexpected_admin_holder_issue_body(email, holder),
        )
        _record_open_escalation(issue)
        slack.post_alert(
            channel=slack_channel,
            message=format_slack_message(
                summary=(
                    "An Okta account holds admin access that wasn't in the "
                    "known-admins list."
                ),
                action=f"Urgent review needed: {email} - respond within 24 hours.",
                issue_url=issue["html_url"],
            ),
            severity="critical",
        )
        newly_reported.append(email_lower)

    if newly_reported:
        put_json_list(reported_param_name, sorted(already_reported | set(newly_reported)))

    return len(newly_reported)


def _record_open_escalation(issue):
    param_name = os.environ["OPEN_ESCALATIONS_PARAM_NAME"]
    records = get_open_escalations(param_name)
    records.append(
        {
            "issue_number": issue["number"],
            "title": issue["title"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    put_open_escalations(param_name, records)


def check_unacknowledged_escalations(event, context):
    """Second entry point (a separate EventBridge rule, every 6 hours - see
    terraform/modules/okta_drift_auditor): re-checks every escalation issue
    handler() has opened and hasn't seen closed yet. Closed issues are
    dropped from the list; issues still open past ESCALATION_REMINDER_HOURS
    get a Slack reminder every time this runs, until someone closes them."""
    param_name = os.environ["OPEN_ESCALATIONS_PARAM_NAME"]
    records = get_open_escalations(param_name)

    github = GitHubClient(
        token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
        repo=os.environ["GITHUB_REPO"],
    )
    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_PARAM_NAME"]))
    slack_channel = os.environ.get("SLACK_ALERTS_CHANNEL", "#iam-alerts")

    now = datetime.now(timezone.utc)
    still_open = []
    reminders_sent = 0

    for record in records:
        issue = github.get_issue(record["issue_number"])

        if issue["state"] != "open":
            logger.info(
                json.dumps({"escalation_acknowledged": {"issue_number": record["issue_number"]}})
            )
            continue

        opened_at = datetime.fromisoformat(record["opened_at"])
        hours_open = (now - opened_at).total_seconds() / 3600

        if hours_open > ESCALATION_REMINDER_HOURS:
            slack.post_alert(
                channel=slack_channel,
                message=format_slack_message(
                    summary=(
                        f"An escalation has been open for {hours_open:.1f} hours "
                        "without being acknowledged."
                    ),
                    action=f"Please review and close: \"{issue['title']}\"",
                    issue_url=issue["html_url"],
                ),
                severity="critical",
            )
            logger.info(
                json.dumps(
                    {
                        "escalation_reminder_sent": {
                            "issue_number": record["issue_number"],
                            "hours_open": round(hours_open, 1),
                        }
                    }
                )
            )
            reminders_sent += 1

        still_open.append(record)

    put_open_escalations(param_name, still_open)

    summary = {"checked": len(records), "reminders_sent": reminders_sent, "still_open": len(still_open)}
    logger.info(json.dumps({"escalation_check_summary": summary}))
    return summary


def _format_issue_body(log_event, log_entry):
    technical_details = "\n".join(
        [
            f"- **Event type:** {log_entry['event_type']}",
            f"- **When:** {log_entry['event_time']}",
            f"- **Actor:** {log_entry['actor']} ({log_entry['actor_type']})",
            f"- **Target(s):** {', '.join(log_entry['targets'])}",
            f"- **Outcome:** {(log_event.get('outcome') or {}).get('result')}",
            "",
            "<details><summary>Raw Okta System Log event</summary>",
            "",
            "```json",
            json.dumps(log_event, indent=2),
            "```",
            "</details>",
        ]
    )

    return format_issue_body(
        what_happened=(
            "A change was made directly in Okta by a person rather than going "
            "through the normal automated process. This needs to be reviewed "
            "and either approved or reversed."
        ),
        what_needs_to_happen=[
            "Review the change details below.",
            "If the change is correct, update the Terraform config to match "
            "and close this issue with a note explaining why.",
            "If the change should not have happened, revert it in Okta and "
            "close this issue with a note.",
        ],
        technical_details=technical_details,
    )


def _format_admin_grant_issue_body(log_event, log_entry):
    role_target = find_admin_role_target(log_event)
    other_targets = [t for t in log_event.get("target", []) or [] if t is not role_target]
    target_user = (
        other_targets[0].get("displayName") or other_targets[0].get("id")
        if other_targets
        else "(unknown)"
    )
    role_type = role_target.get("displayName") if role_target else "(unknown)"

    technical_details = "\n".join(
        [
            f"- **Actor who granted access:** {log_entry['actor']} ({log_entry['actor_type']})",
            f"- **Target user:** {target_user}",
            f"- **Role type granted:** {role_type}",
            f"- **Timestamp:** {log_entry['event_time']}",
            f"- **Okta event ID:** {log_event.get('uuid', '(unknown)')}",
        ]
    )

    return format_issue_body(
        what_happened=(
            "Administrator access was granted to an Okta account outside of "
            "the normal approval process. This is a high-priority security "
            "event that requires immediate review."
        ),
        what_needs_to_happen=[
            "Confirm whether this access grant was authorized and expected.",
            "If authorized: update the admin roles Terraform module to "
            "declare this access formally, and close this issue with the "
            "name of who approved it and why.",
            "If not authorized: remove the admin role in Okta immediately, "
            "investigate how it was granted, and close this issue with a "
            "full incident note.",
            "If you are unsure: escalate to your security team immediately "
            "before taking any other action.",
        ],
        technical_details=technical_details,
        deadline="This requires a response within 24 hours.",
    )


def _format_unexpected_admin_holder_issue_body(email, holder):
    role_types = holder.get("roles") or holder.get("admin_roles") or "(not provided by the API response)"

    technical_details = "\n".join(
        [
            f"- **Account:** {email}",
            f"- **Role type(s) held:** {role_types}",
            "- **Detected by:** the drift auditor's periodic admin-role audit, "
            "not a live grant event - this account may have held this access "
            "before the auditor was ever running.",
        ]
    )

    return format_issue_body(
        what_happened=(
            "An Okta account currently holds administrator access that "
            "wasn't recognized as expected. This may have been granted "
            "before monitoring started, or outside the normal approval "
            "process."
        ),
        what_needs_to_happen=[
            "Confirm whether this access grant was authorized and expected.",
            "If authorized: update the admin roles Terraform module to "
            "declare this access formally, and add this email to "
            "KNOWN_ADMIN_EMAILS.",
            "If not authorized: remove the admin role in Okta immediately, "
            "investigate how it was granted, and close this issue with a "
            "full incident note.",
            "If you are unsure: escalate to your security team immediately "
            "before taking any other action.",
        ],
        technical_details=technical_details,
        deadline="This requires a response within 24 hours.",
    )
=======
def _format_issue_body(log_event, log_entry):
    lines = [
        "A change to a Terraform-managed Okta resource was made outside of "
        "the provisioning Lambda and the Terraform/CI pipeline.",
        "",
        f"- **Event type:** {log_entry['event_type']}",
        f"- **When:** {log_entry['event_time']}",
        f"- **Actor:** {log_entry['actor']} ({log_entry['actor_type']})",
        f"- **Target(s):** {', '.join(log_entry['targets'])}",
        f"- **Outcome:** {(log_event.get('outcome') or {}).get('result')}",
        "",
        "Review whether this should be reverted to match Terraform config, or "
        "imported into Terraform state instead - see `docs/drift-detection.md` "
        "for the two options.",
        "",
        "<details><summary>Raw Okta System Log event</summary>",
        "",
        "```json",
        json.dumps(log_event, indent=2),
        "```",
        "</details>",
    ]
    return "\n".join(lines)
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
