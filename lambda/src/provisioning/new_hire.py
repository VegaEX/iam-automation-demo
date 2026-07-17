import json
import logging
import os

from clients.okta_client import OktaClient
from schema_validator import SchemaValidator, ValidationError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_validator = SchemaValidator()


def process_new_hire(payload):
    """Entry point for a new-hire ADP payload.

    Validation/normalization runs before anything else. A malformed payload
    must fail loudly - re-raised so the Lambda returns a 400 and the event
    lands in the dead letter queue - rather than silently provisioning a
    user from bad data or dropping the event unnoticed.
    """
    try:
        result = _validator.validate_and_normalize(payload)
    except ValidationError as exc:
        logger.error(
            json.dumps(
                {
                    "new_hire_validation_error": {
                        "field": exc.field,
                        "reason": exc.reason,
                        "employee_id": payload.get("employee_id"),
                    }
                }
            )
        )
        raise

    normalized = result.normalized_payload

    okta = OktaClient()
    user_id = okta.create_user(normalized)
    okta.activate_user(user_id)
    okta.assign_to_groups(user_id, normalized["department"])

    logger.info(
        json.dumps(
            {
                "new_hire_provisioned": {
                    "employee_id": normalized["employee_id"],
                    "okta_user_id": user_id,
                }
            }
        )
    )

    return {"okta_user_id": user_id, "validation_result": result}
