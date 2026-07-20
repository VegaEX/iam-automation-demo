import requests


def list_admin_role_holders(org_url, api_token):
    """Return every Okta user who currently holds at least one admin role,
    via the IAM assignees API. Less exercised elsewhere in this project than
    the System Log/Groups endpoints - verify this response shape against a
    real org before relying on it in production."""
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
    profile = holder.get("profile") or {}
    return profile.get("email") or holder.get("email")
