import json
import logging
import os

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

    # TODO: not yet implemented - create/activate the Okta user from
    # result.normalized_payload (see clients/okta_client.py) and assign
    # group membership based on department/employment_type.
    return result
