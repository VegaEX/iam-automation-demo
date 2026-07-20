import json
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from clients import okta_client as okta_client_module  # noqa: E402
from clients.okta_client import OktaApiError, OktaClient  # noqa: E402

NORMALIZED_PAYLOAD = {
    "employee_id": "E12345",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada.lovelace@acme-corp.example",
    "department": "Engineering",
    "title": "",
    "manager_email": None,
    "start_date": "2026-08-01",
    "employment_type": "full_time",
    "cost_center": "",
    "phone": "",
}


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OKTA_ORG_NAME", "test-org")
    monkeypatch.setenv("OKTA_BASE_URL", "okta.com")
    monkeypatch.setenv("OKTA_API_TOKEN_PARAM_NAME", "/iam-automation-demo/okta/api_token")


def _fake_response(status_code, json_body=None, text=None):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = json_body if json_body is not None else {}
    response.text = text if text is not None else json.dumps(json_body or {})
    return response


def test_create_user_maps_profile_and_returns_id(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request:
        mock_request.return_value = _fake_response(200, {"id": "00u123", "status": "STAGED"})

        client = OktaClient()
        user_id = client.create_user(NORMALIZED_PAYLOAD)

        assert user_id == "00u123"
        method, url = mock_request.call_args[0]
        assert method == "POST"
        assert url.endswith("/api/v1/users")

        sent_profile = mock_request.call_args.kwargs["json"]["profile"]
        assert sent_profile["firstName"] == "Ada"
        assert sent_profile["lastName"] == "Lovelace"
        assert sent_profile["email"] == "ada.lovelace@acme-corp.example"
        assert sent_profile["login"] == "ada.lovelace@acme-corp.example"
        assert sent_profile["employeeNumber"] == "E12345"
        # manager_email was None (optional, not provided) - must not appear.
        assert "managerId" not in sent_profile


def test_create_user_api_error_raises_and_logs(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request, patch.object(okta_client_module.time, "sleep") as mock_sleep:
        mock_request.return_value = _fake_response(500, {"errorSummary": "Internal Server Error"})

        client = OktaClient()
        with pytest.raises(OktaApiError) as exc_info:
            client.create_user(NORMALIZED_PAYLOAD)

        assert exc_info.value.status_code == 500
        assert exc_info.value.endpoint == "/api/v1/users"
        assert "Internal Server Error" in exc_info.value.response_body
        # A 500 is retryable, so this exhausted all 3 retries (4 requests
        # total) before finally raising.
        assert mock_request.call_count == 4
        assert mock_sleep.call_count == 3


def test_assign_to_groups_maps_department_and_assigns(monkeypatch):
    _set_required_env(monkeypatch)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET" and url.endswith("/api/v1/groups"):
            name = kwargs["params"]["q"]
            return _fake_response(200, [{"id": f"grp-{name}", "profile": {"name": name}}])
        if method == "PUT":
            return _fake_response(204, {})
        raise AssertionError(f"unexpected request {method} {url}")

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        assigned = client.assign_to_groups("00u123", "Engineering")

        assert assigned == ["all-staff", "eng-base"]


def test_assign_to_groups_unrecognized_department_only_gets_all_staff(monkeypatch):
    _set_required_env(monkeypatch)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET" and url.endswith("/api/v1/groups"):
            name = kwargs["params"]["q"]
            return _fake_response(200, [{"id": f"grp-{name}", "profile": {"name": name}}])
        return _fake_response(204, {})

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        assigned = client.assign_to_groups("00u123", "Marketing")

        assert assigned == ["all-staff"]


def test_deactivate_user_not_found_returns_none(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request:
        mock_request.return_value = _fake_response(404, {}, text="Not found")

        client = OktaClient()
        result = client.deactivate_user("nobody@acme-corp.example")

        assert result is None


def test_deactivate_user_found_deactivates_and_returns_id(monkeypatch):
    _set_required_env(monkeypatch)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET":
            return _fake_response(200, {"id": "00u456", "status": "ACTIVE"})
        assert method == "POST"
        assert url.endswith("/lifecycle/deactivate")
        return _fake_response(200, {})

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        result = client.deactivate_user("leaving@acme-corp.example")

        assert result == "00u456"


def test_remove_from_all_groups_skips_built_in(monkeypatch):
    _set_required_env(monkeypatch)

    groups_response = _fake_response(
        200,
        [
            {"id": "everyone-id", "type": "BUILT_IN", "profile": {"name": "Everyone"}},
            {"id": "eng-id", "type": "OKTA_GROUP", "profile": {"name": "eng-base"}},
        ],
    )
    delete_response = _fake_response(204, {})
    call_log = []

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        call_log.append((method, url))
        if method == "GET":
            return groups_response
        return delete_response

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        removed = client.remove_from_all_groups("00u123")

        assert removed == ["eng-base"]
        delete_calls = [c for c in call_log if c[0] == "DELETE"]
        assert len(delete_calls) == 1
        assert "everyone-id" not in delete_calls[0][1]
        assert "eng-id" in delete_calls[0][1]


def test_initiate_offboarding_full_sequence(monkeypatch):
    _set_required_env(monkeypatch)

    base_url = "https://test-org.okta.com"
    user_id = "00u1"
    email = "ada@acme-corp.example"
    encoded_email = quote(email, safe="")

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET" and url == f"{base_url}/api/v1/users/{encoded_email}":
            return _fake_response(200, {"id": user_id, "profile": {"login": email}})
        if method == "POST" and url == f"{base_url}/api/v1/users/{user_id}/lifecycle/deactivate":
            return _fake_response(200, {})
        if method == "DELETE" and url == f"{base_url}/api/v1/users/{user_id}/sessions":
            return _fake_response(204, {})
        if method == "POST" and url == f"{base_url}/api/v1/users/{user_id}":
            return _fake_response(200, {})
        if method == "GET" and url == f"{base_url}/api/v1/groups":
            return _fake_response(
                200, [{"id": "grp-pending", "profile": {"name": "pending_removal"}}]
            )
        if method == "PUT" and url == f"{base_url}/api/v1/groups/grp-pending/users/{user_id}":
            return _fake_response(204, {})
        if method == "GET" and url == f"{base_url}/api/v1/users/{user_id}/groups":
            return _fake_response(
                200,
                [
                    {"id": "grp-pending", "type": "OKTA_GROUP", "profile": {"name": "pending_removal"}},
                    {"id": "grp-eng", "type": "OKTA_GROUP", "profile": {"name": "eng-base"}},
                ],
            )
        if method == "DELETE" and url == f"{base_url}/api/v1/groups/grp-eng/users/{user_id}":
            return _fake_response(204, {})
        raise AssertionError(f"unexpected request: {method} {url}")

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        result = client.initiate_offboarding(email, "manager@acme-corp.example")

        assert result["user_id"] == user_id
        assert result["original_login"] == email
        assert result["new_login"] == f"{email}_deactivated"
        assert result["removal_date"] is not None


def test_initiate_offboarding_user_not_found_returns_none(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request:
        mock_request.return_value = _fake_response(404, {}, text="Not found")

        client = OktaClient()
        result = client.initiate_offboarding("ghost@acme-corp.example", "manager@acme-corp.example")

        assert result is None


def test_move_to_holding_group_adds_to_pending_removal_and_removes_others(monkeypatch):
    _set_required_env(monkeypatch)

    base_url = "https://test-org.okta.com"
    user_id = "00u123"

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET" and url == f"{base_url}/api/v1/groups":
            return _fake_response(
                200, [{"id": "grp-pending", "profile": {"name": "pending_removal"}}]
            )
        if method == "PUT" and url == f"{base_url}/api/v1/groups/grp-pending/users/{user_id}":
            return _fake_response(204, {})
        if method == "GET" and url == f"{base_url}/api/v1/users/{user_id}/groups":
            return _fake_response(
                200,
                [
                    {"id": "grp-pending", "type": "OKTA_GROUP", "profile": {"name": "pending_removal"}},
                    {"id": "grp-ops", "type": "OKTA_GROUP", "profile": {"name": "ops-base"}},
                    {"id": "everyone-id", "type": "BUILT_IN", "profile": {"name": "Everyone"}},
                ],
            )
        if method == "DELETE" and url == f"{base_url}/api/v1/groups/grp-ops/users/{user_id}":
            return _fake_response(204, {})
        raise AssertionError(f"unexpected request: {method} {url}")

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        removed = client.move_to_holding_group(user_id)

        assert removed == ["ops-base"]


def test_permanently_delete_user_calls_delete_and_returns_id(monkeypatch):
    _set_required_env(monkeypatch)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        if method == "GET":
            return _fake_response(200, {"id": "00u1"})
        assert method == "DELETE"
        return _fake_response(204, {})

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=fake_request
    ):
        client = OktaClient()
        result = client.permanently_delete_user("ada@acme-corp.example")

        assert result == "00u1"


def test_permanently_delete_user_not_found_returns_none(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request:
        mock_request.return_value = _fake_response(404, {}, text="Not found")

        client = OktaClient()
        result = client.permanently_delete_user("ghost@acme-corp.example")

        assert result is None


def test_request_retries_on_429_then_succeeds(monkeypatch):
    _set_required_env(monkeypatch)

    responses = [
        _fake_response(429, {"errorSummary": "Too Many Requests"}),
        _fake_response(200, {"id": "00u1"}),
    ]

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request", side_effect=responses
    ) as mock_request, patch.object(okta_client_module.time, "sleep") as mock_sleep:
        client = OktaClient()
        response = client._request("DELETE", "/api/v1/users/00u1")

        assert response.status_code == 200
        assert mock_request.call_count == 2
        mock_sleep.assert_called_once()
        # First retry delay: base 1s * 2^0 = 1s, plus up to 500ms jitter.
        delay = mock_sleep.call_args[0][0]
        assert 1.0 <= delay <= 1.5


def test_request_backoff_doubles_and_gives_up_after_max_retries(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request, patch.object(okta_client_module.time, "sleep") as mock_sleep, patch.object(
        okta_client_module.random, "uniform", return_value=0.0
    ):
        mock_request.return_value = _fake_response(503, {"errorSummary": "Service Unavailable"})

        client = OktaClient()
        with pytest.raises(OktaApiError) as exc_info:
            client._request("GET", "/api/v1/users/00u1")

        assert exc_info.value.status_code == 503
        # 1 initial attempt + 3 retries = 4 requests total.
        assert mock_request.call_count == 4
        # Delays double starting at 1s: 1, 2, 4 (jitter fixed at 0 above).
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]


def test_request_non_retryable_error_raises_immediately(monkeypatch):
    _set_required_env(monkeypatch)

    with patch.object(okta_client_module, "get_secret", return_value="dummy-token"), patch.object(
        okta_client_module.requests, "request"
    ) as mock_request, patch.object(okta_client_module.time, "sleep") as mock_sleep:
        mock_request.return_value = _fake_response(400, {"errorSummary": "Bad Request"})

        client = OktaClient()
        with pytest.raises(OktaApiError) as exc_info:
            client._request("POST", "/api/v1/users")

        assert exc_info.value.status_code == 400
        # Not retryable - exactly one request, no sleeping at all.
        assert mock_request.call_count == 1
        mock_sleep.assert_not_called()
