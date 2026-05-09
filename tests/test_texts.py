import inspect
import sys
import types

import keyboards
import texts

# Test environment may not have VK runtime deps installed; stub them before importing main.
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

vk_api_stub = types.ModuleType("vk_api")
vk_api_stub.VkApi = object
vk_api_bot_longpoll_stub = types.ModuleType("vk_api.bot_longpoll")
vk_api_bot_longpoll_stub.VkBotEventType = types.SimpleNamespace(MESSAGE_NEW="message_new")
vk_api_bot_longpoll_stub.VkBotLongPoll = object
vk_api_exceptions_stub = types.ModuleType("vk_api.exceptions")
vk_api_exceptions_stub.ApiError = Exception
sys.modules.setdefault("vk_api", vk_api_stub)
sys.modules.setdefault("vk_api.bot_longpoll", vk_api_bot_longpoll_stub)
sys.modules.setdefault("vk_api.exceptions", vk_api_exceptions_stub)

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = Exception
requests_stub.request = lambda *args, **kwargs: None
sys.modules.setdefault("requests", requests_stub)

from services.backend_gateway import BackendApiError
import main


def test_city_selection_text():
    assert main.format_city_selected_message("Казань") == "Город выбран: Казань. Теперь покажем партнёров и предложения рядом."


class VerifyGateway:
    def verify_partner(self, vk_user_id, partner_id):
        return {
            "ok": True,
            "partner_name": "Beauty Partner",
            "dynamic_code": "123456",
            "expires_at": "2026-05-08T12:05:00Z",
        }


class NoSubscriptionGateway:
    def verify_partner(self, vk_user_id, partner_id):
        raise BackendApiError("no_subscription")


def test_verify_success_text_mentions_privilege_and_five_minutes():
    message, _keyboard = main.handle_verify_partner(VerifyGateway(), 1, 2)

    assert "✅ Привилегия подтверждена" in message
    assert "Действует 5 минут" in message
    assert "Покажите этот экран сотруднику партнёра." in message


def test_no_subscription_text_is_adapted_to_privilege():
    message, _keyboard = main.handle_verify_partner(NoSubscriptionGateway(), 1, 2)

    assert "Подписка не активна." in message
    assert "воспользоваться привилегией" in message


def test_legacy_terms_are_absent_from_user_texts():
    forbidden_terms = [
        "Авто" + "Клуб",
        "auto" + "club",
        "".join(("auto", "club", "n", "s", "k")),
        "".join(("auto", "club_", "n", "s", "k")),
        "Н" + "СК",
        "".join(("n", "s", "k")),
    ]
    user_text_sources = [
        texts,
        keyboards,
        main.WELCOME_TEXT,
        main.HELP_TEXT,
        main.FALLBACK_TEXT,
        inspect.getsource(main.format_backend_error_message),
        inspect.getsource(main.handle_verify_partner),
    ]
    combined = "\n".join(str(source) for source in user_text_sources)

    for term in forbidden_terms:
        assert term not in combined

from services.web_api_client import WebApiError
from state import get_user_state, get_web_client_token, reset_user_state


class LinkSuccessClient:
    def exchange_vk_link_code(self, vk_user_id, code, bot_token):
        return {
            "access_token": "client-token",
            "user": {"email": "user@example.com", "role": "member"},
        }


class LinkErrorClient:
    def __init__(self, error):
        self.error = error

    def exchange_vk_link_code(self, vk_user_id, code, bot_token):
        raise self.error


def test_link_success_handler_stores_token_user_and_returns_success_text():
    reset_user_state(2001)

    message = main.handle_vk_link_code(LinkSuccessClient(), 2001, "ABC12345", "bot-token")

    assert get_web_client_token(2001) == "client-token"
    assert get_user_state(2001)["web_client_user"] == {"email": "user@example.com", "role": "member"}
    assert "VK привязан к личному кабинету" in message
    assert "user@example.com" in message
    assert "member" in message


def test_link_404_maps_to_code_not_found_ux():
    message = main.handle_vk_link_code(LinkErrorClient(WebApiError("not_found", status_code=404)), 2002, "ABC12345", "bot-token")

    assert "Код привязки не найден" in message


def test_link_401_maps_to_service_auth_ux():
    message = main.handle_vk_link_code(LinkErrorClient(WebApiError("unauthenticated", status_code=401)), 2003, "ABC12345", "bot-token")

    assert "Сервисная авторизация бота не настроена" in message


def test_link_web_unavailable_maps_to_unavailable_ux():
    message = main.handle_vk_link_code(LinkErrorClient(WebApiError("web_unavailable")), 2004, "ABC12345", "bot-token")

    assert "WEB-сервис временно недоступен" in message
