import json
import logging
import os

from provisioning import new_hire, termination

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Blast-radius guard: a single invocation processing a huge batch (a bad
# upstream retry storm, a misconfigured bulk export, etc.) could hammer the
# Okta API and burn through this Lambda's reserved concurrency
# (terraform/modules/lambda_provisioning, reserved_concurrent_executions=10)
# very fast. Reject the whole batch up front instead of partially processing
# a runaway one.
MAX_RECORDS_PER_INVOCATION = 25


class RunawayBatchError(Exception):
    """Raised when a single invocation's event contains more records than
    this Lambda will process at once."""


def handler(event, context):
    """API Gateway (POST /provision) entry point.

    The request body is either a single ADP event object with a top-level
    "event_type" of "new_hire" or "termination", or a batch of those under
    a "records" list.
    """
    body = _parse_body(event)
    records = body.get("records", [body]) if isinstance(body, dict) else body

    if len(records) > MAX_RECORDS_PER_INVOCATION:
        logger.error(
            json.dumps(
                {
                    "runaway_batch_rejected": {
                        "record_count": len(records),
                        "max_allowed": MAX_RECORDS_PER_INVOCATION,
                    }
                }
            )
        )
        raise RunawayBatchError(
            f"event contained {len(records)} records, more than the "
            f"{MAX_RECORDS_PER_INVOCATION} this Lambda will process in a single invocation"
        )

    results = [_dispatch(record) for record in records]
    return results if len(records) > 1 else results[0]


def _parse_body(event):
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)
    return body


def _dispatch(record):
    event_type = record.get("event_type")
    if event_type == "new_hire":
        return new_hire.process_new_hire(record)
    if event_type == "termination":
        return termination.process_termination(record)
    raise ValueError(f"unrecognized event_type: {event_type!r}")
