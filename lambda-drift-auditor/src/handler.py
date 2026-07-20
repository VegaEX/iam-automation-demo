import json
import logging
import os
from datetime import datetime, timedelta, timezone

from classifier import classify_event
from github_client import GitHubClient
from managed_resources import load_managed_resource_ids
from okta_log_client import OktaLogClient
from secret_store import get_secret
from slack_client import SlackClient
from ssm_state_store import get_open_escalations, put_open_escalations

# An escalation still open after this long gets a repeated Slack nag every
# time check_unacknowledged_escalations runs (every 6 hours - see
# terraform/modules/okta_drift_auditor), until someone closes the issue.
ESCALATION_REMINDER_HOURS = 24

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
    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_URL_PARAM_NAME"]))
    slack_channel = os.environ.get("SLACK_ALERTS_CHANNEL", "#iam-alerts")
    managed_ids = load_managed_resource_ids()

    all_events = okta_logs.get_events_since(since)
    relevant_events = [e for e in all_events if e.get("eventType") in RELEVANT_EVENT_TYPES]

    results = {"approved": 0, "escalated": 0, "ignored": 0}

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
        issue = github.create_issue(
            title="Manual Okta change detected — review required",
            body=_format_issue_body(log_event, log_entry),
        )
        _record_open_escalation(issue)
        slack.post_alert(
            channel=slack_channel,
            message=(
                f"Manual Okta change detected: {log_entry['actor']} "
                f"({log_entry['actor_type']}) changed {', '.join(log_entry['targets'])} "
                f"at {log_entry['event_time']}. See the GitHub issue for details."
            ),
            severity="warning",
        )

    logger.info(json.dumps({"drift_audit_summary": results}))
    return results


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
    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_URL_PARAM_NAME"]))
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
                message=(
                    f"Escalation still unacknowledged after {hours_open:.1f}h: "
                    f"\"{issue['title']}\" - {issue['html_url']}"
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
