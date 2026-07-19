import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from clients.secret_store import get_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "adp_schema.json")

# Retry policy for _request(): only 429 (rate limit) and 5xx responses are
# transient enough to be worth retrying - anything else (4xx like 400/401/
# 403/404) means the request itself was wrong and retrying won't help.
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 1
RETRY_JITTER_MAX_SECONDS = 0.5

# eng-base/ops-base already have Terraform-managed dynamic group rules that
# assign users by this same department attribute (see
# terraform/modules/okta_groups) - this mapping is deliberately assigning the
# user directly too, as a belt-and-suspenders measure so the new hire lands
# in the right groups immediately rather than waiting on Okta's rule engine
# to re-evaluate. This call is made with the provisioning Lambda's own Okta
# token, so it's an "SSWS" actor in the System Log, not the "System" actor
# Okta's own rule engine uses - okta-drift-auditor classifies it as
# approved_automation (via KNOWN_AUTOMATION_ACTOR_IDS), a different bucket
# than the rule engine's approved_hr_pattern. See docs/drift-detection.md.
DEPARTMENT_GROUP_MAP = {
    "Engineering": "eng-base",
    "Operations": "ops-base",
}
ALL_STAFF_GROUP = "all-staff"

# Terminated users land here instead of being removed from every group
# outright - it's a real Terraform-managed group (see
# terraform/modules/okta_groups) that scheduled_removal.py's daily sweep
# treats as "awaiting permanent deletion."
HOLDING_GROUP_NAME = "pending_removal"
DEFAULT_OFFBOARDING_HOLD_DAYS = 30


class OktaApiError(Exception):
    """Raised for any non-2xx response from the Okta API."""

    def __init__(self, endpoint, status_code, response_body):
        self.endpoint = endpoint
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"{endpoint} returned {status_code}: {response_body}")


class OktaClient:
    """Thin wrapper around the Okta Users/Groups REST API."""

    def __init__(self, schema_path=None):
        self.org_name = os.environ["OKTA_ORG_NAME"]
        self.base_url = f"https://{self.org_name}.{os.environ['OKTA_BASE_URL']}"
        self._token = None

        schema_path = schema_path or os.environ.get("ADP_SCHEMA_PATH", DEFAULT_SCHEMA_PATH)
        with open(schema_path) as fh:
            self._schema = json.load(fh)

    @property
    def _api_token(self):
        # Fetched lazily, once per client instance - not at import time, and
        # not on every single request.
        if self._token is None:
            self._token = get_secret(os.environ["OKTA_API_TOKEN_PARAM_NAME"])
        return self._token

    def _headers(self):
        return {
            "Authorization": f"SSWS {self._api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method, path=None, url=None, allow_404=False, **kwargs):
        endpoint = path or url
        request_url = url or f"{self.base_url}{path}"

        attempt = 0
        while True:
            response = requests.request(
                method, request_url, headers=self._headers(), timeout=10, **kwargs
            )

            if allow_404 and response.status_code == 404:
                return None

            if response.ok:
                return response

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY_SECONDS * (2**attempt) + random.uniform(
                    0, RETRY_JITTER_MAX_SECONDS
                )
                logger.warning(
                    json.dumps(
                        {
                            "okta_api_retry": {
                                "endpoint": endpoint,
                                "status_code": response.status_code,
                                "attempt": attempt + 1,
                                "max_retries": MAX_RETRIES,
                                "delay_seconds": round(delay, 3),
                            }
                        }
                    )
                )
                time.sleep(delay)
                attempt += 1
                continue

            logger.error(
                json.dumps(
                    {
                        "okta_api_error": {
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "response_body": response.text[:1000],
                        }
                    }
                )
            )
            raise OktaApiError(endpoint, response.status_code, response.text)

    def _map_profile(self, payload):
        profile = {}
        for field_name, field_def in self._schema.items():
            value = payload.get(field_name)
            if value is None:
                continue
            profile[field_def["okta_attribute"]] = value

        # Okta requires profile.login - this ADP feed has no separate
        # username field, so login is always the user's email.
        profile.setdefault("login", payload.get("email"))
        return profile

    def create_user(self, payload):
        """Create an Okta user from a normalized ADP payload.

        Left in Okta's default STAGED status - call activate_user()
        afterward to transition it to ACTIVE. Returns the new user's Okta ID.
        """
        profile = self._map_profile(payload)
        response = self._request("POST", "/api/v1/users", json={"profile": profile})
        return response.json()["id"]

    def activate_user(self, user_id):
        """Activate a user created in STAGED status."""
        self._request(
            "POST",
            f"/api/v1/users/{user_id}/lifecycle/activate",
            params={"sendEmail": "false"},
        )

    def assign_to_groups(self, user_id, department):
        """Assign a user to all-staff plus their department's base group, if
        the department maps to one (Engineering -> eng-base, Operations ->
        ops-base). Unrecognized departments still get all-staff."""
        group_names = [ALL_STAFF_GROUP]
        department_group = DEPARTMENT_GROUP_MAP.get(department)
        if department_group:
            group_names.append(department_group)

        assigned = []
        for group_name in group_names:
            group_id = self._find_group_id_by_name(group_name)
            if group_id is None:
                logger.warning(
                    json.dumps(
                        {"okta_group_not_found": {"group_name": group_name, "user_id": user_id}}
                    )
                )
                continue
            self._request("PUT", f"/api/v1/groups/{group_id}/users/{user_id}")
            assigned.append(group_name)

        return assigned

    def deactivate_user(self, email):
        """Look up a user by email and deactivate them.

        Returns the user's Okta ID, or None if no user with that email
        exists - a missing user is not an error for the termination flow to
        raise on, just a no-op to log and move past.
        """
        user = self._find_user_by_email(email)
        if user is None:
            return None

        user_id = user["id"]
        self._request("POST", f"/api/v1/users/{user_id}/lifecycle/deactivate")
        return user_id

    def remove_from_all_groups(self, user_id):
        """Remove a user from every group except Okta's built-in Everyone
        group, which can't be left directly."""
        removed = []
        for group in self.get_user_groups(user_id):
            if group.get("type") == "BUILT_IN":
                continue
            group_id = group["id"]
            self._request("DELETE", f"/api/v1/groups/{group_id}/users/{user_id}")
            removed.append(group.get("profile", {}).get("name", group_id))

        return removed

    def get_user_groups(self, user_id):
        """Return the raw list of group objects a user currently belongs to."""
        response = self._request("GET", f"/api/v1/users/{user_id}/groups")
        return response.json()

    def clear_sessions(self, user_id):
        """Immediately invalidate every active Okta session for a user, and
        revoke any OAuth/OIDC tokens issued to them, so a deactivation can't
        be outrun by an already-open session."""
        self._request(
            "DELETE", f"/api/v1/users/{user_id}/sessions", params={"oauthTokens": "true"}
        )

    def rename_username(self, user_id, original_login):
        """Rename a user's login to `<original>_deactivated`, freeing the
        original username/address up for reuse without deleting the
        account outright. Returns the new login."""
        new_login = f"{original_login}_deactivated"
        self._request("POST", f"/api/v1/users/{user_id}", json={"profile": {"login": new_login}})
        return new_login

    def move_to_holding_group(self, user_id, holding_group_name=HOLDING_GROUP_NAME):
        """Remove a user from every group except Okta's built-in Everyone
        group and the holding group, and ensure they're a member of the
        holding group. Returns the list of group names removed from."""
        holding_group_id = self._find_group_id_by_name(holding_group_name)
        if holding_group_id is None:
            logger.warning(
                json.dumps(
                    {"okta_group_not_found": {"group_name": holding_group_name, "user_id": user_id}}
                )
            )
        else:
            self._request("PUT", f"/api/v1/groups/{holding_group_id}/users/{user_id}")

        removed = []
        for group in self.get_user_groups(user_id):
            group_name = group.get("profile", {}).get("name")
            if group.get("type") == "BUILT_IN" or group_name == holding_group_name:
                continue
            group_id = group["id"]
            self._request("DELETE", f"/api/v1/groups/{group_id}/users/{user_id}")
            removed.append(group_name or group_id)

        return removed

    def permanently_delete_user(self, email):
        """Permanently delete an already-deactivated user by email. Okta
        requires DELETE to be called on a DEACTIVATED user to actually erase
        the account, rather than merely deactivating it. Returns the
        deleted user's ID, or None if no user with that email exists
        (already gone is not an error)."""
        user = self._find_user_by_email(email)
        if user is None:
            return None

        user_id = user["id"]
        self._request("DELETE", f"/api/v1/users/{user_id}")
        return user_id

    def initiate_offboarding(self, email, manager_email, hold_days=DEFAULT_OFFBOARDING_HOLD_DAYS):
        """Immediately cut Okta access for a departing user - deactivate,
        clear every active session, rename their login, and move them into
        the pending_removal holding group. This is the "security first"
        step that must complete before anything else in the offboarding
        flow (per-app actions, the manager checklist issue) runs.

        Returns None if no user with that email exists - a missing user is
        not an error for the termination flow to raise on, just a no-op to
        log and move past, same contract as deactivate_user.
        """
        user = self._find_user_by_email(email)
        if user is None:
            return None

        user_id = user["id"]
        original_login = user.get("profile", {}).get("login", email)

        self._request("POST", f"/api/v1/users/{user_id}/lifecycle/deactivate")
        self.clear_sessions(user_id)
        new_login = self.rename_username(user_id, original_login)
        self.move_to_holding_group(user_id)

        removal_date = (datetime.now(timezone.utc) + timedelta(days=hold_days)).date().isoformat()
        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info(
            json.dumps(
                {
                    "offboarding_initiated": {
                        "user_id": user_id,
                        "employee_email": email,
                        "manager_email": manager_email,
                        "timestamp": timestamp,
                        "removal_date": removal_date,
                    }
                }
            )
        )

        return {
            "user_id": user_id,
            "original_login": original_login,
            "new_login": new_login,
            "removal_date": removal_date,
        }

    def list_active_users(self):
        """Return every user with status ACTIVE, following pagination
        (Link: rel="next") to completion."""
        response = self._request(
            "GET", "/api/v1/users", params={"filter": 'status eq "ACTIVE"', "limit": 200}
        )
        users = list(response.json())

        next_url = response.links.get("next", {}).get("url")
        while next_url:
            response = self._request("GET", url=next_url)
            users.extend(response.json())
            next_url = response.links.get("next", {}).get("url")

        return users

    def _find_user_by_email(self, email):
        path = f"/api/v1/users/{quote(email, safe='')}"
        response = self._request("GET", path, allow_404=True)
        return response.json() if response is not None else None

    def _find_group_id_by_name(self, name):
        response = self._request("GET", "/api/v1/groups", params={"q": name})
        for group in response.json():
            if group.get("profile", {}).get("name") == name:
                return group["id"]
        return None
