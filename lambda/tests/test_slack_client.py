import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from clients import slack_client as slack_client_module  # noqa: E402
from clients.slack_client import SlackClient  # noqa: E402


def _fake_response(status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.text = ""
    return response


@pytest.mark.parametrize(
    "severity,expected_color",
    [
        ("info", "#009688"),
        ("warning", "#ff9800"),
        ("critical", "#f44336"),
    ],
)
def test_post_alert_uses_correct_severity_color(severity, expected_color):
    with patch.object(slack_client_module.requests, "post") as mock_post:
        mock_post.return_value = _fake_response(200)

        client = SlackClient(webhook_url="https://hooks.slack.example/services/T000/B000/xxx")
        client.post_alert(channel="#iam-alerts", message="something happened", severity=severity)

        _, kwargs = mock_post.call_args
        attachment = kwargs["json"]["attachments"][0]
        assert attachment["color"] == expected_color
        assert attachment["text"] == "something happened"
        assert kwargs["json"]["channel"] == "#iam-alerts"


def test_post_alert_rejects_unknown_severity():
    client = SlackClient(webhook_url="https://hooks.slack.example/services/T000/B000/xxx")

    with pytest.raises(ValueError):
        client.post_alert(channel="#iam-alerts", message="oops", severity="urgent")


def test_post_alert_raises_on_http_error():
    with patch.object(slack_client_module.requests, "post") as mock_post:
        response = _fake_response(500)
        response.raise_for_status.side_effect = Exception("500 error")
        mock_post.return_value = response

        client = SlackClient(webhook_url="https://hooks.slack.example/services/T000/B000/xxx")

        with pytest.raises(Exception):
            client.post_alert(channel="#iam-alerts", message="oops", severity="critical")
