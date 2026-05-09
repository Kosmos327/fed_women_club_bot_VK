from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


RequestsTimeout = getattr(requests, "Timeout", getattr(requests, "RequestException", Exception))
RequestsConnectionError = getattr(requests, "ConnectionError", getattr(requests, "RequestException", Exception))
RequestsRequestException = getattr(requests, "RequestException", Exception)


class _UnavailableSession:
    def request(self, *args: Any, **kwargs: Any) -> Any:
        raise RequestsRequestException("requests Session is unavailable")


def _default_session() -> Any:
    session_class = getattr(requests, "Session", None)
    if session_class is None:
        return _UnavailableSession()
    return session_class()


@dataclass
class WebApiError(Exception):
    code: str
    status_code: int | None = None
    detail: str | None = None

    def __str__(self) -> str:
        if self.detail:
            return f"{self.code}: {self.detail}"
        return self.code


class WebApiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 10, session: Any | None = None):
        self.base_url = self._normalize_base_url(base_url)
        self.root_url = self._root_from_base_url(self.base_url)
        self.api_base_url = f"{self.root_url}/api/v1"
        self.timeout_seconds = timeout_seconds
        self.session = session or _default_session()

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        return (base_url or "").strip().rstrip("/")

    @staticmethod
    def _root_from_base_url(base_url: str) -> str:
        parsed = urlsplit(base_url)
        path = parsed.path.rstrip("/")
        if path == "/api/v1":
            path = ""
        root = parsed._replace(path=path, query="", fragment="")
        return urlunsplit(root).rstrip("/")

    def _build_api_url(self, path: str) -> str:
        normalized_path = "/" + path.strip("/")
        if normalized_path.startswith("/api/v1/") or normalized_path == "/api/v1":
            return f"{self.root_url}{normalized_path}"
        return f"{self.api_base_url}{normalized_path}"

    def build_public_url(self, path: str) -> str:
        normalized_path = "/" + path.strip("/")
        return f"{self.root_url}{normalized_path}"

    def health(self) -> Any:
        return self.request("GET", "/health")

    def request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self._build_api_url(path)
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                json=json,
                params=params,
                timeout=self.timeout_seconds,
            )
        except (RequestsTimeout, RequestsConnectionError, RequestsRequestException) as exc:
            raise WebApiError("web_unavailable", detail=str(exc)) from exc

        payload = self._parse_response(response)
        if response.status_code >= 400:
            raise WebApiError(
                self._map_status_code(response.status_code),
                status_code=response.status_code,
                detail=self._extract_detail(payload),
            )
        return payload

    def get_client_me(self, token: str) -> Any:
        return self.request("GET", "/clients/me", token=token)

    def get_client_catalog_partners(
        self,
        token: str,
        city_slug: str | None = None,
        category_slug: str | None = None,
        q: str | None = None,
    ) -> Any:
        params = {
            key: value
            for key, value in {
                "city_slug": city_slug,
                "category_slug": category_slug,
                "q": q,
            }.items()
            if value is not None
        }
        return self.request("GET", "/clients/catalog/partners", token=token, params=params or None)

    def create_partner_verification(
        self,
        token: str,
        partner_id: int,
        offer_id: int | None = None,
        source: str = "vk",
    ) -> Any:
        body = {"partner_id": partner_id, "source": source}
        if offer_id is not None:
            body["offer_id"] = offer_id
        return self.request("POST", "/clients/partner-verifications", token=token, json=body)

    @staticmethod
    def _parse_response(response: Any) -> Any:
        if getattr(response, "status_code", None) == 204:
            return None
        content = getattr(response, "content", None)
        text = getattr(response, "text", "")
        if content == b"" or (content is None and text == ""):
            return None
        try:
            return response.json()
        except ValueError:
            return text

    @staticmethod
    def _extract_detail(payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("detail", "message", "code"):
                value = payload.get(key)
                if value is not None:
                    return str(value)
            return None
        if payload is None:
            return None
        return str(payload)

    @staticmethod
    def _map_status_code(status_code: int) -> str:
        if status_code == 401:
            return "unauthenticated"
        if status_code == 403:
            return "forbidden"
        if status_code == 404:
            return "not_found"
        if status_code == 422:
            return "validation_error"
        if status_code >= 500:
            return "server_error"
        if status_code >= 400:
            return "client_error"
        return "ok"
