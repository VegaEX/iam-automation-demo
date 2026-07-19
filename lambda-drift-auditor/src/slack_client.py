import json
import logging
import os

import requests

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Slack attachment "color" accepts any hex string - these are just
# conventional info/warning/critical colors, not a Slack-defined enum.
SEVERITY_COLORS = {
    "info": "#009688",  # teal
    "warning": "#ff9800",  # orange
    "critical": "#f44336",  # red
}


class SlackClient:
    """Thin wrapper around a Slack incoming webhook."""

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def post_alert(self, channel, message, severity="info"):
        if severity not in SEVERITY_COLORS:
            raise ValueError(f"unknown severity: {severity!r}")

        payload = {
            "channel": channel,
            "attachments": [{"color": SEVERITY_COLORS[severity], "text": message}],
        }

        response = requests.post(self.webhook_url, json=payload, timeout=10)
        if not response.ok:
            logger.error(
                json.dumps(
                    {
                        "slack_api_error": {
                            "channel": channel,
                            "status_code": response.status_code,
                            "response_body": response.text[:1000],
                        }
                    }
                )
            )
            response.raise_for_status()

        logger.info(json.dumps({"slack_alert_posted": {"channel": channel, "severity": severity}}))
        return response
