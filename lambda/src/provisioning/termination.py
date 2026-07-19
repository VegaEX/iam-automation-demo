import json
import logging
import os

import offboarding_manager
from clients.okta_client import OktaClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def process_termination(payload):
    """Entry point for a termination payload.

    Sequence matters here: Okta access and sessions are cut first (security
    first), then the account is renamed and moved to the pending_removal
    holding group, and only after all of that completes does
    offboarding_manager run the per-app actions, Google Workspace
    delegation, and open the manager checklist issue.

    A user not found by email is not an error worth failing the Lambda
    over (e.g. the account may have already been deactivated by a prior
    retry) - it's logged as a warning and the function returns cleanly.
    """
    email = payload["email"]
    manager_email = payload.get("manager_email")
    employee_name = payload.get("employee_name")

    okta = OktaClient()
    hold_days = offboarding_manager.resolve_hold_days()

    offboarding_result = okta.initiate_offboarding(email, manager_email, hold_days=hold_days)
    if offboarding_result is None:
        logger.warning(json.dumps({"termination_user_not_found": {"email": email}}))
        return {"email": email, "found": False}

    checklist_result = offboarding_manager.run_offboarding(
        user_email=email,
        manager_email=manager_email,
        employee_name=employee_name,
        removal_date=offboarding_result["removal_date"],
    )

    logger.info(
        json.dumps(
            {
                "termination_processed": {
                    "email": email,
                    "okta_user_id": offboarding_result["user_id"],
                    "new_login": offboarding_result["new_login"],
                    "removal_date": offboarding_result["removal_date"],
                    "manual_items": [item["app"] for item in checklist_result["manual_items"]],
                    "github_issue_number": checklist_result["github_issue"].get("number"),
                }
            }
        )
    )

    return {
        "email": email,
        "okta_user_id": offboarding_result["user_id"],
        "found": True,
        "removal_date": offboarding_result["removal_date"],
        "manual_items_count": len(checklist_result["manual_items"]),
    }
