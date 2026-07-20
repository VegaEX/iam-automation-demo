import json
import logging
import os
from datetime import date, datetime, timezone

from clients.github_client import GitHubClient
from clients.okta_client import OktaClient
from clients.secret_store import get_secret
from clients.slack_client import SlackClient
from clients.ssm_state_store import get_pending_removals, put_pending_removals
from issue_format import format_issue_body, format_slack_message

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def run_scheduled_removal():
    """Daily sweep over the pending-removals list: permanently delete any
    Okta user whose hold period has elapsed, and leave everyone else in
    place, logging how many days they have left."""
    param_name = os.environ["PENDING_REMOVALS_PARAM_NAME"]
    records = get_pending_removals(param_name)

    today = datetime.now(timezone.utc).date()
    okta = OktaClient()
    github = GitHubClient(
        token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
        repo=os.environ["GITHUB_REPO"],
    )
    slack = SlackClient(webhook_url=get_secret(os.environ["SLACK_WEBHOOK_PARAM_NAME"]))
    slack_channel = os.environ.get("SLACK_ALERTS_CHANNEL", "#iam-alerts")

    remaining_records = []
    removed_emails = []

    for record in records:
        removal_date = date.fromisoformat(record["removal_date"])

        if removal_date > today:
            days_remaining = (removal_date - today).days
            logger.info(
                json.dumps(
                    {
                        "scheduled_removal_check": {
                            "email": record["email"],
                            "removal_date": record["removal_date"],
                            "days_remaining": days_remaining,
                        }
                    }
                )
            )
            remaining_records.append(record)
            continue

        okta.permanently_delete_user(record["email"])

        logger.info(
            json.dumps(
                {
                    "scheduled_removal_completed": {
                        "email": record["email"],
                        "removal_date": record["removal_date"],
                    }
                }
            )
        )

        issue_number = record.get("github_issue_number")
        if issue_number:
            github.add_comment(
                issue_number,
                _format_completion_comment(record, today),
            )
            issue_url = f"https://github.com/{os.environ['GITHUB_REPO']}/issues/{issue_number}"
            slack.post_alert(
                channel=slack_channel,
                message=format_slack_message(
                    summary=(
                        f"The Okta account for {record['email']} was permanently "
                        "deleted, as scheduled."
                    ),
                    action="No action needed - informational only.",
                    issue_url=issue_url,
                ),
                severity="info",
            )

        removed_emails.append(record["email"])

    put_pending_removals(param_name, remaining_records)

    return {"removed": removed_emails, "remaining": len(remaining_records)}


def _format_completion_comment(record, today):
    return format_issue_body(
        what_happened=(
            f"The Okta account for {record['email']} was permanently deleted "
            "today, as scheduled. This is the final step of the offboarding "
            "process."
        ),
        what_needs_to_happen=["No further action is needed - this issue can stay closed."],
        technical_details=(
            f"- **Email:** {record['email']}\n"
            f"- **Scheduled removal date:** {record['removal_date']}\n"
            f"- **Actual deletion date:** {today.isoformat()}"
        ),
    )


def handler(event, context):
    return run_scheduled_removal()
