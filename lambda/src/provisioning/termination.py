import json
import logging
import os

from clients.okta_client import OktaClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def process_termination(payload):
    """Entry point for a termination payload - deactivates the Okta user
    identified by email and removes their group memberships.

    A user not found by email is not an error worth failing the Lambda
    over (e.g. the account may have already been deactivated by a prior
    retry) - it's logged as a warning and the function returns cleanly.
    """
    email = payload["email"]
    okta = OktaClient()

    user_id = okta.deactivate_user(email)
    if user_id is None:
        logger.warning(json.dumps({"termination_user_not_found": {"email": email}}))
        return {"email": email, "found": False}

    okta.remove_from_all_groups(user_id)

    logger.info(
        json.dumps(
            {
                "termination_processed": {
                    "email": email,
                    "okta_user_id": user_id,
                }
            }
        )
    )

    return {"email": email, "okta_user_id": user_id, "found": True}
