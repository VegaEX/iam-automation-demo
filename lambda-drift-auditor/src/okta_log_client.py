import requests


class OktaLogClient:
    """Thin wrapper around the Okta System Log API (GET /api/v1/logs)."""

    def __init__(self, org_url, api_token):
        self.org_url = org_url.rstrip("/")
        self.api_token = api_token

    def get_events_since(self, since):
        """Return every System Log event published at or after `since`
        (a timezone-aware datetime), following pagination to completion."""
        events = []
        url = f"{self.org_url}/api/v1/logs"
        params = {
            "since": since.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "sortOrder": "ASCENDING",
        }
        headers = {
            "Authorization": f"SSWS {self.api_token}",
            "Accept": "application/json",
        }

        while url:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            events.extend(response.json())

            # The `next` Link header carries its own fully-encoded query
            # string (including an updated `since` cursor), so params must
            # only be sent on the first request.
            url = response.links.get("next", {}).get("url")
            params = None

        return events
