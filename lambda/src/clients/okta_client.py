import json
import logging
import os
from urllib.parse import quote

import requests

from clients.secret_store import get_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "adp_schema.json")

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

    def _request(self, method, path, allow_404=False, **kwargs):
        url = f"{self.base_url}{path}"
        response = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)

        if allow_404 and response.status_code == 404:
            return None

        if not response.ok:
            logger.error(
                json.dumps(
                    {
                        "okta_api_error": {
                            "endpoint": path,
                            "status_code": response.status_code,
                            "response_body": response.text[:1000],
                        }
                    }
                )
            )
            raise OktaApiError(path, response.status_code, response.text)

        return response

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
        response = self._request("GET", f"/api/v1/users/{user_id}/groups")

        removed = []
        for group in response.json():
            if group.get("type") == "BUILT_IN":
                continue
            group_id = group["id"]
            self._request("DELETE", f"/api/v1/groups/{group_id}/users/{user_id}")
            removed.append(group.get("profile", {}).get("name", group_id))

        return removed

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
