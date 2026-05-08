from __future__ import annotations

from typing import Any

import requests


class BackendApiError(Exception):
    def __init__(self, code: str, status_code: int | None = None, message: str | None = None):
        super().__init__(message or code)
        self.code = code
        self.status_code = status_code


class BackendGateway:
    def __init__(self, base_url: str, bot_api_token: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.bot_api_token = bot_api_token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bot_api_token}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(method, url, headers=self.headers, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise BackendApiError("backend_unavailable", message=str(exc)) from exc
        if response.status_code >= 400:
            code = "backend_error"
            try:
                payload = response.json()
                code = payload.get("code") or payload.get("detail") or code
            except ValueError:
                pass
            raise BackendApiError(str(code), status_code=response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def health(self) -> Any:
        return self._request("GET", "health")

    def auth_vk_user(self, vk_user_id: int, first_name: str | None = None, last_name: str | None = None, screen_name: str | None = None) -> Any:
        return self._request("POST", "bot/vk/auth", json={"vk_user_id": vk_user_id, "first_name": first_name, "last_name": last_name, "screen_name": screen_name})

    def get_categories(self) -> list[dict]:
        return self._request("GET", "bot/categories") or []

    def get_partners(self, category: str | None = None, limit: int = 10, offset: int = 0) -> list[dict]:
        params = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category
        return self._request("GET", "bot/partners", params=params) or []

    def get_partner(self, partner_id: int) -> dict:
        return self._request("GET", f"bot/partners/{partner_id}") or {}

    def get_partner_services(self, partner_id: int) -> list[dict]:
        return self._request("GET", f"bot/partners/{partner_id}/services") or []

    def search_services(self, query: str) -> list[dict]:
        return self._request("GET", "bot/services/search", params={"q": query}) or []

    def request_discount_code(self, vk_user_id: int, partner_id: int, service_id: int) -> dict:
        return self._request("POST", "bot/codes", json={"vk_user_id": vk_user_id, "partner_id": partner_id, "service_id": service_id}) or {}

    def get_my_codes(self, vk_user_id: int, status: str | None = None) -> list[dict]:
        params = {"vk_user_id": vk_user_id}
        if status:
            params["status"] = status
        return self._request("GET", "bot/codes", params=params) or []

    def get_subscription(self, vk_user_id: int) -> dict:
        return self._request("GET", "bot/subscription", params={"vk_user_id": vk_user_id}) or {}

    def get_latest_payment_request(self, vk_user_id: int) -> dict | None:
        return self._request("GET", "bot/payments/latest", params={"vk_user_id": vk_user_id})

    def create_payment_request(self, vk_user_id: int) -> dict:
        return self._request("POST", "bot/payments", json={"vk_user_id": vk_user_id}) or {}

    def mark_payment_paid(self, vk_user_id: int, payment_request_id: int | None = None) -> Any:
        return self._request("POST", "bot/payments/paid", json={"vk_user_id": vk_user_id, "payment_request_id": payment_request_id})

    def attach_payment_receipt(self, vk_user_id: int, file_url: str) -> Any:
        return self._request("POST", "bot/payments/receipt", json={"vk_user_id": vk_user_id, "file_url": file_url})

    def verify_partner(self, vk_user_id: int | str, partner_id: int) -> dict:
        return self._request("POST", "bot/partners/verify", json={"vk_user_id": vk_user_id, "partner_id": partner_id}) or {}
