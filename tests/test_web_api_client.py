import pytest
import requests

from config import load_config
from services.web_api_client import WebApiClient, WebApiError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", json_error=False):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self._json_error = json_error
        self.content = text.encode() if text else b"payload"

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, exception=None):
        self.response = response or FakeResponse(payload={"ok": True})
        self.exception = exception
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.exception:
            raise self.exception
        return self.response


def _set_required_config_env(monkeypatch):
    monkeypatch.setenv("VK_GROUP_TOKEN", "test-token")
    monkeypatch.setenv("VK_GROUP_ID", "123")
    monkeypatch.setenv("ADMIN_ID", "456")
    monkeypatch.setenv("BOT_API_TOKEN", "test-api-token")
    monkeypatch.delenv("WEB_API_BASE_URL", raising=False)
    monkeypatch.delenv("WEB_API_TIMEOUT_SECONDS", raising=False)


def test_config_exposes_web_api_base_url_default(monkeypatch):
    _set_required_config_env(monkeypatch)

    config = load_config()

    assert config.web_api_base_url == "https://bloomclub.ru"


def test_config_exposes_web_api_timeout_seconds_default(monkeypatch):
    _set_required_config_env(monkeypatch)

    config = load_config()

    assert config.web_api_timeout_seconds == 10


@pytest.mark.parametrize(
    "base_url",
    [
        "https://bloomclub.ru",
        "https://bloomclub.ru/",
        "https://bloomclub.ru/api/v1",
    ],
)
def test_health_builds_api_v1_health_url_from_supported_base_urls(base_url):
    session = FakeSession(response=FakeResponse(payload={"status": "ok"}))
    client = WebApiClient(base_url, session=session)

    client.health()

    assert session.calls[0]["url"] == "https://bloomclub.ru/api/v1/health"


def test_request_accepts_path_already_prefixed_with_api_v1():
    session = FakeSession(response=FakeResponse(payload={"status": "ok"}))
    client = WebApiClient("https://bloomclub.ru/", session=session)

    client.request("GET", "/api/v1/health")

    assert session.calls[0]["url"] == "https://bloomclub.ru/api/v1/health"


def test_request_adds_authorization_header_only_when_token_provided():
    session = FakeSession(response=FakeResponse(payload={"ok": True}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.request("GET", "/health")
    client.request("GET", "/health", token="client-token")

    assert "Authorization" not in session.calls[0]["headers"]
    assert session.calls[1]["headers"]["Authorization"] == "Bearer client-token"


def test_request_sends_timeout():
    session = FakeSession(response=FakeResponse(payload={"ok": True}))
    client = WebApiClient("https://bloomclub.ru", timeout_seconds=7, session=session)

    client.request("GET", "/health")

    assert session.calls[0]["timeout"] == 7


def test_health_returns_parsed_json():
    session = FakeSession(response=FakeResponse(payload={"status": "ok"}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.health() == {"status": "ok"}


def test_timeout_or_request_exception_maps_to_web_unavailable():
    client = WebApiClient(
        "https://bloomclub.ru",
        session=FakeSession(exception=requests.RequestException("timed out")),
    )

    with pytest.raises(WebApiError) as exc_info:
        client.health()

    assert exc_info.value.code == "web_unavailable"
    assert exc_info.value.status_code is None


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "unauthenticated"),
        (403, "forbidden"),
        (404, "not_found"),
        (422, "validation_error"),
        (500, "server_error"),
    ],
)
def test_status_errors_map_to_web_api_error_codes(status_code, expected_code):
    response = FakeResponse(status_code=status_code, payload={"detail": "failed"})
    client = WebApiClient("https://bloomclub.ru", session=FakeSession(response=response))

    with pytest.raises(WebApiError) as exc_info:
        client.health()

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == "failed"


def test_build_public_url_uses_root_public_path():
    client = WebApiClient("https://bloomclub.ru/api/v1/")

    assert client.build_public_url("/r/p/test") == "https://bloomclub.ru/r/p/test"


def test_exchange_vk_link_code_builds_correct_request():
    session = FakeSession(response=FakeResponse(payload={"access_token": "client-token"}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.exchange_vk_link_code(123, "ABC12345", "bot-service-token")

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://bloomclub.ru/api/v1/bot/vk/exchange-link-code"
    assert call["headers"]["Authorization"] == "Bearer bot-service-token"
    assert call["json"] == {"vk_user_id": "123", "code": "ABC12345"}


def test_get_vk_bound_token_builds_correct_request():
    session = FakeSession(response=FakeResponse(payload={"access_token": "client-token"}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.get_vk_bound_token(123, "bot-service-token")

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://bloomclub.ru/api/v1/bot/vk/token"
    assert call["headers"]["Authorization"] == "Bearer bot-service-token"
    assert call["json"] == {"vk_user_id": "123"}


def test_get_client_subscription_builds_correct_authorized_request():
    session = FakeSession(response=FakeResponse(payload={"has_active_subscription": True}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.get_client_subscription("client-token") == {"has_active_subscription": True}

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://bloomclub.ru/api/v1/clients/me/subscription"
    assert call["headers"]["Authorization"] == "Bearer client-token"


def test_onboard_vk_client_builds_correct_request_with_city_slug():
    session = FakeSession(response=FakeResponse(payload={"access_token": "client-token"}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.onboard_vk_client(123, "bot-service-token", selected_city_slug="novosibirsk")

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://bloomclub.ru/api/v1/bot/vk/onboard-client"
    assert call["headers"]["Authorization"] == "Bearer bot-service-token"
    assert call["json"]["vk_user_id"] == "123"
    assert call["json"]["source"] == "vk"
    assert call["json"]["selected_city_slug"] == "novosibirsk"
    assert call["json"]["full_name"] is None


def test_onboard_vk_client_returns_password_setup_fields_unfiltered():
    payload = {
        "access_token": "client-token",
        "user": {"id": 10},
        "client": {"id": 20},
        "is_new": True,
        "password_setup_url": "https://bloomclub.ru/password/setup?token=one-time-token",
        "login": "user@example.com",
        "password_setup_expires_at": "2026-05-11T12:00:00Z",
        "password_setup_ttl_seconds": 3600,
        "password_setup_required": True,
    }
    session = FakeSession(response=FakeResponse(payload=payload))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.onboard_vk_client(123, "bot-service-token") == payload


def test_get_client_verifications_builds_authorized_request_without_status_by_default():
    session = FakeSession(response=FakeResponse(payload=[{"code": "A1"}]))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.get_client_verifications("client-token") == [{"code": "A1"}]

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://bloomclub.ru/api/v1/clients/me/verifications"
    assert call["headers"]["Authorization"] == "Bearer client-token"
    assert call["params"] is None


def test_get_client_verifications_passes_active_status_query():
    session = FakeSession(response=FakeResponse(payload=[]))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.get_client_verifications("client-token", status="active")

    assert session.calls[0]["params"] == {"status": "active"}


@pytest.mark.parametrize("status", [None, "all"])
def test_get_client_verifications_omits_all_or_none_status_query(status):
    session = FakeSession(response=FakeResponse(payload=[]))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.get_client_verifications("client-token", status=status)

    assert session.calls[0]["params"] is None


def test_get_client_profile_builds_correct_authorized_request():
    session = FakeSession(response=FakeResponse(payload={"id": 7, "selected_city_slug": "novosibirsk"}))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.get_client_profile("client-token") == {"id": 7, "selected_city_slug": "novosibirsk"}

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://bloomclub.ru/api/v1/clients/me"
    assert call["headers"]["Authorization"] == "Bearer client-token"


def test_get_client_catalog_partners_builds_authorized_request_with_filters():
    payload = [{"id": 1, "name": "Beauty"}]
    session = FakeSession(response=FakeResponse(payload=payload))
    client = WebApiClient("https://bloomclub.ru", session=session)

    assert client.get_client_catalog_partners(
        "client-token",
        city_slug="novosibirsk",
        category_slug="beauty",
        q="spa",
    ) == payload

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://bloomclub.ru/api/v1/clients/catalog/partners"
    assert call["headers"]["Authorization"] == "Bearer client-token"
    assert call["params"] == {"city_slug": "novosibirsk", "category_slug": "beauty", "q": "spa"}


def test_get_client_catalog_partners_omits_empty_filters():
    session = FakeSession(response=FakeResponse(payload=[]))
    client = WebApiClient("https://bloomclub.ru", session=session)

    client.get_client_catalog_partners("client-token")

    assert session.calls[0]["params"] is None
