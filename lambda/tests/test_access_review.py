import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import access_review  # noqa: E402

NOW = datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _user(user_id, email, department, created, last_login=None):
    return {
        "id": user_id,
        "created": _iso(created),
        "lastLogin": _iso(last_login) if last_login else None,
        "profile": {"email": email, "department": department},
    }


def _groups(*names):
    return [{"profile": {"name": name}} for name in names]


def _set_required_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-demo/github-token")
    monkeypatch.setenv("GITHUB_REPO", "acme-corp/iam-automation-demo")
    monkeypatch.setenv("SLACK_WEBHOOK_PARAM_NAME", "/iam-demo/slack-webhook")


def _run_with_mocks(monkeypatch, users, groups_by_user_id):
    _set_required_env(monkeypatch)

    with patch.object(access_review, "OktaClient") as mock_okta_cls, patch.object(
        access_review, "GitHubClient"
    ) as mock_gh_cls, patch.object(access_review, "SlackClient"), patch.object(
        access_review, "get_secret", return_value="dummy-secret"
    ):
        mock_okta = mock_okta_cls.return_value
        mock_okta.list_active_users.return_value = users
        mock_okta.get_user_groups.side_effect = lambda user_id: groups_by_user_id.get(user_id, [])
        mock_gh_cls.return_value.create_issue.return_value = {
            "number": 1,
            "html_url": "https://github.com/acme-corp/iam-automation-demo/issues/1",
        }

        report = access_review.run_access_review()

        return report, mock_gh_cls.return_value


def test_user_with_correct_group_membership_passes(monkeypatch):
    user = _user(
        "00u1",
        "ada@acme-corp.example",
        "Engineering",
        created=NOW - timedelta(days=400),
        last_login=NOW - timedelta(days=1),
    )
    groups = {"00u1": _groups("eng-base", "all-staff")}

    report, mock_gh = _run_with_mocks(monkeypatch, [user], groups)

    assert report["mismatched_users"] == []
    assert report["stale_users"] == []
    assert report["users_checked"] == 1
    mock_gh.create_issue.assert_not_called()


def test_user_with_mismatched_department_flagged(monkeypatch):
    user = _user(
        "00u2",
        "sam@acme-corp.example",
        "Sales",
        created=NOW - timedelta(days=400),
        last_login=NOW - timedelta(days=1),
    )
    groups = {"00u2": _groups("eng-base", "all-staff")}

    report, mock_gh = _run_with_mocks(monkeypatch, [user], groups)

    assert len(report["mismatched_users"]) == 1
    finding = report["mismatched_users"][0]
    assert finding["user_id"] == "00u2"
    assert finding["email"] == "sam@acme-corp.example"
    assert "eng-base" in finding["reason"]
    assert "Sales" in finding["reason"]
    mock_gh.create_issue.assert_called_once()
    _, kwargs = mock_gh.create_issue.call_args
    assert kwargs["title"] == "Access review findings — manual review required"
    assert "00u2" in kwargs["body"]


def test_user_with_no_login_in_91_days_flagged(monkeypatch):
    user = _user(
        "00u3",
        "stale@acme-corp.example",
        "Engineering",
        created=NOW - timedelta(days=500),
        last_login=NOW - timedelta(days=91),
    )
    groups = {"00u3": _groups("eng-base", "all-staff")}

    report, mock_gh = _run_with_mocks(monkeypatch, [user], groups)

    assert len(report["stale_users"]) == 1
    stale = report["stale_users"][0]
    assert stale["user_id"] == "00u3"
    assert stale["days_since_login"] == 91
    mock_gh.create_issue.assert_called_once()


def test_user_created_yesterday_with_no_login_not_flagged(monkeypatch):
    user = _user(
        "00u4",
        "newhire@acme-corp.example",
        "Engineering",
        created=NOW - timedelta(days=1),
        last_login=None,
    )
    groups = {"00u4": _groups("eng-base", "all-staff")}

    report, mock_gh = _run_with_mocks(monkeypatch, [user], groups)

    assert report["stale_users"] == []
    assert report["mismatched_users"] == []
    mock_gh.create_issue.assert_not_called()


def test_empty_org_returns_clean_report(monkeypatch):
    report, mock_gh = _run_with_mocks(monkeypatch, [], {})

    assert report == {
        "checked_at": report["checked_at"],
        "users_checked": 0,
        "mismatched_users": [],
        "stale_users": [],
    }
    mock_gh.create_issue.assert_not_called()
