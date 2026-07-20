import requests


def list_admin_role_holders(org_url, api_token):
    """Return every user currently holding at least one Okta admin role, via
    the IAM role-assignees API, following pagination to completion.

    This "list every admin role holder org-wide" use case is exercised far
    less elsewhere in this project than the per-resource endpoints (Users,
    Groups, System Log) are, and Okta's IAM roles/governance API has shifted
    over time - verify this endpoint's exact path and each entry's exact
    shape against the current Okta API reference before relying on it in
    production. Each returned entry is expected to carry the user's email
    under `profile.email` (or, as a fallback some API versions use, a
    top-level `email`) - handled defensively by the caller either way.
    """
    headers = {"Authorization": f"SSWS {api_token}", "Accept": "application/json"}
    url = f"{org_url}/api/v1/iam/assignees/users"
    holders = []

    while url:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        holders.extend(response.json())
        url = response.links.get("next", {}).get("url")

    return holders


def get_holder_email(holder):
    """Best-effort extraction of a role-assignee's email across the couple
    of response shapes this endpoint might return."""
    profile = holder.get("profile") or {}
    return profile.get("email") or holder.get("email")
