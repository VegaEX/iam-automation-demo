import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import offboarding_manager  # noqa: E402
from issue_format import format_human_date  # noqa: E402


def _set_required_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_PARAM_NAME", "/iam-demo/github-token")
    monkeypatch.setenv("GITHUB_REPO", "acme-corp/iam-automation-demo")
    monkeypatch.setenv("PENDING_REMOVALS_PARAM_NAME", "/iam-demo/pending-removals")
    monkeypatch.setenv("SLACK_WEBHOOK_PARAM_NAME", "/iam-demo/slack-webhook")


def _mocked_run_offboarding(monkeypatch, **kwargs):
    with patch.object(offboarding_manager, "GitHubClient") as mock_gh_cls, patch.object(
        offboarding_manager, "GoogleWorkspaceClient"
    ) as mock_google_cls, patch.object(offboarding_manager, "SlackClient"), patch.object(
        offboarding_manager, "get_secret", return_value="dummy-secret"
    ), patch.object(offboarding_manager, "get_pending_removals", return_value=[]), patch.object(
        offboarding_manager, "put_pending_removals"
    ) as mock_put_pending:
        mock_gh = mock_gh_cls.return_value
        mock_gh.create_issue.return_value = {
            "number": 42,
            "html_url": "https://github.com/acme-corp/iam-automation-demo/issues/42",
        }

        mock_google = mock_google_cls.return_value
        mock_google.delegate_inbox.return_value = {"status": "DELEGATION_ACTIVE"}
        mock_google.rename_account.return_value = {"status": "RENAMED"}
        mock_google.transfer_drive.return_value = {"status": "TRANSFER_QUEUED"}
        mock_google.create_hidden_group.return_value = {"status": "GROUP_CREATED"}
        mock_google.schedule_deletion.return_value = {"status": "DELETION_SCHEDULED"}

        result = offboarding_manager.run_offboarding(**kwargs)

        return result, mock_gh, mock_google, mock_put_pending


def test_offboarding_manager_executes_correct_actions_per_app(monkeypatch):
    _set_required_env(monkeypatch)

    result, mock_gh, mock_google, mock_put_pending = _mocked_run_offboarding(
        monkeypatch,
        user_email="departed@acme-corp.example",
        manager_email="manager@acme-corp.example",
        employee_name="Jamie Doe",
    )

    automatic_apps = {a["app"] for a in result["automatic_actions"]}
    manual_apps = {m["app"] for m in result["manual_items"]}

    assert automatic_apps == {"slack", "google_workspace"}
    assert manual_apps == {"github", "salesforce", "atlassian"}

    mock_google.delegate_inbox.assert_called_once_with(
        "departed@acme-corp.example", "manager@acme-corp.example"
    )
    mock_google.rename_account.assert_called_once_with(
        "departed@acme-corp.example", "departed_deactivated"
    )
    mock_google.transfer_drive.assert_called_once_with(
        "departed@acme-corp.example", "manager@acme-corp.example"
    )
    mock_google.schedule_deletion.assert_called_once_with("departed@acme-corp.example", days=30)

    mock_gh.create_issue.assert_called_once()
    _, kwargs = mock_gh.create_issue.call_args
    assert kwargs["title"] == "Offboarding checklist — Jamie Doe"
    assert "departed@acme-corp.example" in kwargs["body"]
    assert format_human_date(result["removal_date"]) in kwargs["body"]

    mock_put_pending.assert_called_once()
    _, records = mock_put_pending.call_args[0]
    assert records[-1]["email"] == "departed@acme-corp.example"
    assert records[-1]["manager_email"] == "manager@acme-corp.example"
    assert records[-1]["github_issue_number"] == 42


def test_manual_checklist_items_collected_for_github_and_salesforce(monkeypatch):
    _set_required_env(monkeypatch)

    result, _, _, _ = _mocked_run_offboarding(
        monkeypatch,
        user_email="departed@acme-corp.example",
        manager_email="manager@acme-corp.example",
    )

    manual_by_app = {item["app"]: item for item in result["manual_items"]}

    assert manual_by_app["github"]["action"] == "remove_org_membership"
    assert "GitHub organization" in manual_by_app["github"]["instructions"]
    assert "departed@acme-corp.example" in manual_by_app["github"]["instructions"]

    assert manual_by_app["salesforce"]["action"] == "deactivate"
    assert "Salesforce" in manual_by_app["salesforce"]["instructions"]
    assert "departed@acme-corp.example" in manual_by_app["salesforce"]["instructions"]


def test_resolve_hold_days_reads_from_config():
    assert offboarding_manager.resolve_hold_days() == 30
