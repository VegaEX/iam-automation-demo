import json
import logging
import os
from datetime import datetime, timezone

from clients.github_client import GitHubClient
from clients.okta_client import DEPARTMENT_GROUP_MAP, OktaClient
from clients.secret_store import get_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

STALE_LOGIN_DAYS = 90
STALE_NEVER_LOGGED_IN_DAYS = 7

# Reverse of OktaClient's DEPARTMENT_GROUP_MAP (eng-base -> Engineering, ...),
# so a user's group memberships can be checked against what their department
# implies just as easily as the other way around.
GROUP_DEPARTMENT_MAP = {group: department for department, group in DEPARTMENT_GROUP_MAP.items()}


def _parse_okta_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_group_mismatches(department, current_group_names):
    """Return a list of {"expected_group", "reason"} dicts - empty if the
    user's department and group memberships agree."""
    findings = []

    for group_name in current_group_names:
        expected_department = GROUP_DEPARTMENT_MAP.get(group_name)
        if expected_department and department != expected_department:
            findings.append(
                {
                    "expected_group": None,
                    "reason": (
                        f"member of {group_name} but department is "
                        f"{department!r}, expected {expected_department!r}"
                    ),
                }
            )

    expected_group = DEPARTMENT_GROUP_MAP.get(department)
    if expected_group and expected_group not in current_group_names:
        findings.append(
            {
                "expected_group": expected_group,
                "reason": f"department is {department!r} but not a member of {expected_group}",
            }
        )

    return findings


def _check_stale_access(user, now):
    """Return a stale-access finding dict, or None if the user isn't stale."""
    last_login = user.get("lastLogin")

    if last_login:
        days_since_login = (now - _parse_okta_timestamp(last_login)).days
        if days_since_login > STALE_LOGIN_DAYS:
            return {
                "last_login": last_login,
                "days_since_login": days_since_login,
                "reason": f"last login {days_since_login} days ago",
            }
        return None

    days_since_created = (now - _parse_okta_timestamp(user["created"])).days
    if days_since_created > STALE_NEVER_LOGGED_IN_DAYS:
        return {
            "last_login": None,
            "days_since_login": days_since_created,
            "reason": f"never logged in, created {days_since_created} days ago",
        }
    return None


def run_access_review():
    """Fetch every active Okta user, flag group/department mismatches and
    stale accounts, log the full report, and open a GitHub issue if there's
    anything to review. Returns the report dict."""
    okta = OktaClient()
    now = datetime.now(timezone.utc)

    mismatched_users = []
    stale_users = []
    users_checked = 0

    for user in okta.list_active_users():
        users_checked += 1
        user_id = user["id"]
        profile = user.get("profile", {})
        email = profile.get("email")
        department = profile.get("department")

        current_groups = [
            group["profile"]["name"]
            for group in okta.get_user_groups(user_id)
            if group.get("profile", {}).get("name")
        ]

        for finding in _check_group_mismatches(department, current_groups):
            mismatched_users.append(
                {
                    "user_id": user_id,
                    "email": email,
                    "current_groups": current_groups,
                    "expected_group": finding["expected_group"],
                    "reason": finding["reason"],
                }
            )

        stale = _check_stale_access(user, now)
        if stale is not None:
            stale_users.append({"user_id": user_id, "email": email, **stale})

    report = {
        "checked_at": now.isoformat(),
        "users_checked": users_checked,
        "mismatched_users": mismatched_users,
        "stale_users": stale_users,
    }

    logger.info(json.dumps({"access_review_report": report}))

    if mismatched_users or stale_users:
        _open_findings_issue(report)

    return report


def _format_issue_body(report):
    lines = [
        f"Automated access review checked {report['users_checked']} active user(s) as of "
        f"{report['checked_at']} and found {len(report['mismatched_users'])} group "
        f"mismatch(es) and {len(report['stale_users'])} stale account(s).",
        "",
    ]

    if report["mismatched_users"]:
        lines += [
            "### Group membership mismatches",
            "",
            "| User ID | Email | Current Groups | Expected Group | Reason |",
            "|---|---|---|---|---|",
        ]
        for m in report["mismatched_users"]:
            groups = ", ".join(m["current_groups"]) or "(none)"
            expected = m["expected_group"] or "(none)"
            lines.append(f"| {m['user_id']} | {m['email']} | {groups} | {expected} | {m['reason']} |")
        lines.append("")

    if report["stale_users"]:
        lines += [
            "### Stale accounts",
            "",
            "| User ID | Email | Last Login | Days Since Login |",
            "|---|---|---|---|",
        ]
        for s in report["stale_users"]:
            last_login = s["last_login"] or "never"
            lines.append(f"| {s['user_id']} | {s['email']} | {last_login} | {s['days_since_login']} |")
        lines.append("")

    lines.append(
        "Review each finding and either correct the user's group membership or "
        "department in the HR system, or deactivate the account if it's no "
        "longer needed."
    )
    return "\n".join(lines)


def _open_findings_issue(report):
    github = GitHubClient(
        token=get_secret(os.environ["GITHUB_TOKEN_PARAM_NAME"]),
        repo=os.environ["GITHUB_REPO"],
    )
    github.create_issue(
        title="Access review findings — manual review required",
        body=_format_issue_body(report),
    )
    logger.info(
        json.dumps(
            {
                "access_review_issue_opened": {
                    "mismatched_count": len(report["mismatched_users"]),
                    "stale_count": len(report["stale_users"]),
                }
            }
        )
    )


def handler(event, context):
    report = run_access_review()
    return {
        "users_checked": report["users_checked"],
        "mismatched_count": len(report["mismatched_users"]),
        "stale_count": len(report["stale_users"]),
    }
