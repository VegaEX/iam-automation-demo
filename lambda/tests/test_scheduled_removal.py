import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scheduled_removal  # noqa: E402


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OKTA_ORG_NAME", "test-org")
    monkeypatch.setenv("OKTA_BASE_URL", "okta.com")
    monkeypatch.setenv("OKTA_API_TOKEN_PARAM_NAME", "/iam-demo/okta/api_token")
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-demo/github-token")
    monkeypatch.setenv("GITHUB_REPO", "acme-corp/iam-automation-demo")
    monkeypatch.setenv("PENDING_REMOVALS_PARAM_NAME", "/iam-demo/pending-removals")
    monkeypatch.setenv("SLACK_WEBHOOK_PARAM_NAME", "/iam-demo/slack-webhook")


def test_scheduled_removal_fires_for_overdue_and_skips_in_window(monkeypatch):
    _set_required_env(monkeypatch)
    today = datetime.now(timezone.utc).date()

    overdue_record = {
        "email": "overdue@acme-corp.example",
        "manager_email": "manager@acme-corp.example",
        "removal_date": (today - timedelta(days=1)).isoformat(),
        "github_issue_number": 99,
    }
    in_window_record = {
        "email": "recent@acme-corp.example",
        "manager_email": "manager@acme-corp.example",
        "removal_date": (today + timedelta(days=10)).isoformat(),
        "github_issue_number": 100,
    }

    with patch.object(
        scheduled_removal, "get_pending_removals", return_value=[overdue_record, in_window_record]
    ), patch.object(scheduled_removal, "put_pending_removals") as mock_put, patch.object(
        scheduled_removal, "OktaClient"
    ) as mock_okta_cls, patch.object(
        scheduled_removal, "GitHubClient"
    ) as mock_gh_cls, patch.object(
        scheduled_removal, "SlackClient"
    ) as mock_slack_cls, patch.object(
        scheduled_removal, "get_secret", return_value="dummy-secret"
    ):
        mock_okta = mock_okta_cls.return_value
        mock_okta.permanently_delete_user.return_value = "00u_overdue"
        mock_gh = mock_gh_cls.return_value
        mock_slack = mock_slack_cls.return_value

        result = scheduled_removal.run_scheduled_removal()

        mock_okta.permanently_delete_user.assert_called_once_with("overdue@acme-corp.example")

        mock_gh.add_comment.assert_called_once()
        args, _ = mock_gh.add_comment.call_args
        assert args[0] == 99
        assert "overdue@acme-corp.example" in args[1]

        mock_slack.post_alert.assert_called_once()
        _, slack_kwargs = mock_slack.post_alert.call_args
        assert slack_kwargs["severity"] == "info"
        assert "overdue@acme-corp.example" in slack_kwargs["message"]
        assert "issues/99" in slack_kwargs["message"]

        assert result["removed"] == ["overdue@acme-corp.example"]
        assert result["remaining"] == 1

        mock_put.assert_called_once()
        _, remaining_records = mock_put.call_args[0]
        assert remaining_records == [in_window_record]


def test_scheduled_removal_deletes_nothing_when_all_within_hold_window(monkeypatch):
    _set_required_env(monkeypatch)
    today = datetime.now(timezone.utc).date()

    in_window_record = {
        "email": "recent@acme-corp.example",
        "manager_email": "manager@acme-corp.example",
        "removal_date": (today + timedelta(days=29)).isoformat(),
        "github_issue_number": 101,
    }

    with patch.object(
        scheduled_removal, "get_pending_removals", return_value=[in_window_record]
    ), patch.object(scheduled_removal, "put_pending_removals") as mock_put, patch.object(
        scheduled_removal, "OktaClient"
    ) as mock_okta_cls, patch.object(
        scheduled_removal, "GitHubClient"
    ) as mock_gh_cls, patch.object(
        scheduled_removal, "SlackClient"
    ) as mock_slack_cls, patch.object(
        scheduled_removal, "get_secret", return_value="dummy-secret"
    ):
        mock_okta = mock_okta_cls.return_value
        mock_gh = mock_gh_cls.return_value
        mock_slack = mock_slack_cls.return_value

        result = scheduled_removal.run_scheduled_removal()

        mock_okta.permanently_delete_user.assert_not_called()
        mock_gh.add_comment.assert_not_called()
        mock_slack.post_alert.assert_not_called()
        assert result == {"removed": [], "remaining": 1}
        mock_put.assert_called_once_with(os.environ["PENDING_REMOVALS_PARAM_NAME"], [in_window_record])
