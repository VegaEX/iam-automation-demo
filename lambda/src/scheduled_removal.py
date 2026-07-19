import json
import logging
import os
from datetime import date, datetime, timezone

from clients.github_client import GitHubClient
from clients.okta_client import OktaClient
from clients.secret_store import get_secret
from clients.ssm_state_store import get_pending_removals, put_pending_removals

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
                f"Scheduled removal complete: the Okta account for {record['email']} "
                f"was permanently deleted on {today.isoformat()}, as scheduled.",
            )

        removed_emails.append(record["email"])

    put_pending_removals(param_name, remaining_records)

    return {"removed": removed_emails, "remaining": len(remaining_records)}


def handler(event, context):
    return run_scheduled_removal()
