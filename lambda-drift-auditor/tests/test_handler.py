import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import handler  # noqa: E402


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OKTA_ORG_NAME", "test-org")
    monkeypatch.setenv("OKTA_BASE_URL", "okta.com")
    monkeypatch.setenv("OKTA_API_TOKEN_PARAM_NAME", "/iam-automation-demo/okta/api_token")
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-automation-demo/github/token")
    monkeypatch.setenv("GITHUB_REPO", "acme/iam-automation-demo")
    monkeypatch.setenv("SLACK_WEBHOOK_URL_PARAM_NAME", "/iam-automation-demo/slack/webhook_url")
    monkeypatch.setenv(
        "OPEN_ESCALATIONS_PARAM_NAME", "/iam-automation-demo/drift-auditor/open-escalations"
    )
    monkeypatch.setenv(
        "MANAGED_RESOURCE_IDS_JSON",
        json.dumps({"group_ids": {"eng-base": "00gtracked"}}),
    )
    monkeypatch.setenv("KNOWN_AUTOMATION_ACTOR_IDS", "00tautomation")


def test_manual_change_to_managed_resource_opens_issue_and_posts_to_slack(monkeypatch):
    _set_required_env(monkeypatch)

    manual_event = {
        "eventType": "group.profile.update",
        "published": "2026-07-15T08:05:00.000Z",
        "actor": {"id": "00uhuman", "type": "User", "displayName": "Jane Admin"},
        "target": [{"id": "00gtracked", "displayName": "eng-base"}],
        "outcome": {"result": "SUCCESS"},
    }

    with patch.object(handler, "OktaLogClient") as mock_okta_cls, patch.object(
        handler, "GitHubClient"
    ) as mock_gh_cls, patch.object(handler, "SlackClient") as mock_slack_cls, patch.object(
        handler, "get_secret", return_value="dummy-secret"
    ), patch.object(handler, "get_open_escalations", return_value=[]), patch.object(
        handler, "put_open_escalations"
    ) as mock_put_escalations:
        mock_okta_cls.return_value.get_events_since.return_value = [manual_event]
        mock_gh = mock_gh_cls.return_value
        mock_gh.create_issue.return_value = {
            "number": 123,
            "title": "Manual Okta change detected — review required",
        }
        mock_slack = mock_slack_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 0, "escalated": 1, "ignored": 0}
        mock_gh.create_issue.assert_called_once()
        _, kwargs = mock_gh.create_issue.call_args
        assert kwargs["title"] == "Manual Okta change detected — review required"
        assert "Jane Admin" in kwargs["body"]

        mock_slack.post_alert.assert_called_once()
        _, slack_kwargs = mock_slack.post_alert.call_args
        assert slack_kwargs["severity"] == "warning"
        assert "Jane Admin" in slack_kwargs["message"]
        assert "eng-base" in slack_kwargs["message"]

        # The escalation was recorded for later follow-up.
        mock_put_escalations.assert_called_once()
        _, recorded = mock_put_escalations.call_args[0]
        assert recorded[0]["issue_number"] == 123


def test_automation_change_is_approved_without_issue_or_slack(monkeypatch):
    _set_required_env(monkeypatch)

    automation_event = {
        "eventType": "group.user_membership.add",
        "published": "2026-07-15T08:05:00.000Z",
        "actor": {"id": "00tautomation", "type": "SSWS", "displayName": "terraform-ci"},
        "target": [{"id": "00gtracked", "displayName": "eng-base"}],
        "outcome": {"result": "SUCCESS"},
    }

    with patch.object(handler, "OktaLogClient") as mock_okta_cls, patch.object(
        handler, "GitHubClient"
    ) as mock_gh_cls, patch.object(handler, "SlackClient") as mock_slack_cls, patch.object(
        handler, "get_secret", return_value="dummy-secret"
    ):
        mock_okta_cls.return_value.get_events_since.return_value = [automation_event]
        mock_gh = mock_gh_cls.return_value
        mock_slack = mock_slack_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 1, "escalated": 0, "ignored": 0}
        mock_gh.create_issue.assert_not_called()
        mock_slack.post_alert.assert_not_called()


def test_change_to_unmanaged_resource_is_ignored(monkeypatch):
    _set_required_env(monkeypatch)

    unrelated_event = {
        "eventType": "group.profile.update",
        "published": "2026-07-15T08:05:00.000Z",
        "actor": {"id": "00uhuman", "type": "User", "displayName": "Jane Admin"},
        "target": [{"id": "00gnottracked", "displayName": "some-other-group"}],
        "outcome": {"result": "SUCCESS"},
    }

    with patch.object(handler, "OktaLogClient") as mock_okta_cls, patch.object(
        handler, "GitHubClient"
    ) as mock_gh_cls, patch.object(handler, "SlackClient") as mock_slack_cls, patch.object(
        handler, "get_secret", return_value="dummy-secret"
    ):
        mock_okta_cls.return_value.get_events_since.return_value = [unrelated_event]
        mock_gh = mock_gh_cls.return_value
        mock_slack = mock_slack_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 0, "escalated": 0, "ignored": 1}
        mock_gh.create_issue.assert_not_called()
        mock_slack.post_alert.assert_not_called()


def test_check_unacknowledged_escalations_reminds_for_issue_open_over_24h(monkeypatch):
    _set_required_env(monkeypatch)

    stale_opened_at = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    record = {"issue_number": 123, "title": "Manual Okta change detected — review required", "opened_at": stale_opened_at}

    with patch.object(handler, "get_open_escalations", return_value=[record]), patch.object(
        handler, "put_open_escalations"
    ) as mock_put, patch.object(handler, "GitHubClient") as mock_gh_cls, patch.object(
        handler, "SlackClient"
    ) as mock_slack_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_gh = mock_gh_cls.return_value
        mock_gh.get_issue.return_value = {
            "state": "open",
            "title": record["title"],
            "html_url": "https://github.com/acme/iam-automation-demo/issues/123",
        }
        mock_slack = mock_slack_cls.return_value

        summary = handler.check_unacknowledged_escalations({}, None)

        mock_gh.get_issue.assert_called_once_with(123)
        mock_slack.post_alert.assert_called_once()
        _, slack_kwargs = mock_slack.post_alert.call_args
        assert slack_kwargs["severity"] == "critical"
        assert "123" in slack_kwargs["message"] or "issues/123" in slack_kwargs["message"]

        assert summary == {"checked": 1, "reminders_sent": 1, "still_open": 1}
        mock_put.assert_called_once_with(os.environ["OPEN_ESCALATIONS_PARAM_NAME"], [record])


def test_check_unacknowledged_escalations_skips_issue_within_24h(monkeypatch):
    _set_required_env(monkeypatch)

    recent_opened_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    record = {"issue_number": 124, "title": "Recent escalation", "opened_at": recent_opened_at}

    with patch.object(handler, "get_open_escalations", return_value=[record]), patch.object(
        handler, "put_open_escalations"
    ) as mock_put, patch.object(handler, "GitHubClient") as mock_gh_cls, patch.object(
        handler, "SlackClient"
    ) as mock_slack_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_gh = mock_gh_cls.return_value
        mock_gh.get_issue.return_value = {
            "state": "open",
            "title": record["title"],
            "html_url": "https://github.com/acme/iam-automation-demo/issues/124",
        }
        mock_slack = mock_slack_cls.return_value

        summary = handler.check_unacknowledged_escalations({}, None)

        mock_slack.post_alert.assert_not_called()
        assert summary == {"checked": 1, "reminders_sent": 0, "still_open": 1}
        mock_put.assert_called_once_with(os.environ["OPEN_ESCALATIONS_PARAM_NAME"], [record])


def test_check_unacknowledged_escalations_drops_closed_issues(monkeypatch):
    _set_required_env(monkeypatch)

    old_opened_at = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    record = {"issue_number": 125, "title": "Now closed", "opened_at": old_opened_at}

    with patch.object(handler, "get_open_escalations", return_value=[record]), patch.object(
        handler, "put_open_escalations"
    ) as mock_put, patch.object(handler, "GitHubClient") as mock_gh_cls, patch.object(
        handler, "SlackClient"
    ) as mock_slack_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_gh = mock_gh_cls.return_value
        mock_gh.get_issue.return_value = {"state": "closed", "title": record["title"], "html_url": "..."}
        mock_slack = mock_slack_cls.return_value

        summary = handler.check_unacknowledged_escalations({}, None)

        mock_slack.post_alert.assert_not_called()
        assert summary == {"checked": 1, "reminders_sent": 0, "still_open": 0}
        mock_put.assert_called_once_with(os.environ["OPEN_ESCALATIONS_PARAM_NAME"], [])
