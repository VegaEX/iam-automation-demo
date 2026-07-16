import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import handler  # noqa: E402


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OKTA_ORG_NAME", "test-org")
    monkeypatch.setenv("OKTA_BASE_URL", "okta.com")
    monkeypatch.setenv("OKTA_API_TOKEN_PARAM_NAME", "/iam-automation-demo/okta/api_token")
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-automation-demo/github/token")
    monkeypatch.setenv("GITHUB_REPO", "acme/iam-automation-demo")
    monkeypatch.setenv(
        "MANAGED_RESOURCE_IDS_JSON",
        json.dumps({"group_ids": {"eng-base": "00gtracked"}}),
    )
    monkeypatch.setenv("KNOWN_AUTOMATION_ACTOR_IDS", "00tautomation")


def test_manual_change_to_managed_resource_opens_issue(monkeypatch):
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
    ) as mock_gh_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_okta_cls.return_value.get_events_since.return_value = [manual_event]
        mock_gh = mock_gh_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 0, "escalated": 1, "ignored": 0}
        mock_gh.create_issue.assert_called_once()
        _, kwargs = mock_gh.create_issue.call_args
        assert kwargs["title"] == "Manual Okta change detected — review required"
        assert "Jane Admin" in kwargs["body"]


def test_automation_change_is_approved_without_issue(monkeypatch):
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
    ) as mock_gh_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_okta_cls.return_value.get_events_since.return_value = [automation_event]
        mock_gh = mock_gh_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 1, "escalated": 0, "ignored": 0}
        mock_gh.create_issue.assert_not_called()


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
    ) as mock_gh_cls, patch.object(handler, "get_secret", return_value="dummy-secret"):
        mock_okta_cls.return_value.get_events_since.return_value = [unrelated_event]
        mock_gh = mock_gh_cls.return_value

        results = handler.handler({}, None)

        assert results == {"approved": 0, "escalated": 0, "ignored": 1}
        mock_gh.create_issue.assert_not_called()
