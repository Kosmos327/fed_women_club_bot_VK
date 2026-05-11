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


def test_backend_error_mapping_keeps_known_business_errors():
    assert main.format_backend_error_message(BackendApiError("no_subscription")) == texts.NO_SUBSCRIPTION_TEXT
    assert main.format_backend_error_message(BackendApiError("payment_request_not_found")) == texts.PAYMENT_REQUEST_NOT_FOUND_TEXT
    assert main.format_backend_error_message(BackendApiError("discount_code_limit_reached")) == texts.PRIVILEGE_LIMIT_REACHED_TEXT


def test_backend_error_mapping_is_user_friendly_without_raw_status_or_code():
    cases = [
        (BackendApiError("backend_unavailable"), "Сервис временно недоступен"),
        (BackendApiError("unauthorized", status_code=401), "Не удалось подтвердить доступ"),
        (BackendApiError("forbidden", status_code=403), "Не удалось подтвердить доступ"),
        (BackendApiError("not_found", status_code=404), "Данные пока не найдены"),
        (BackendApiError("validation_error", status_code=422), "Не удалось обработать запрос"),
        (BackendApiError("internal_error", status_code=500), "На стороне сервиса произошла ошибка"),
    ]

    for error, expected_text in cases:
        message = main.format_backend_error_message(error)

        assert expected_text in message
        assert str(error.status_code) not in message
        assert error.code not in message


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


class JoinSuccessClient:
    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload or {
            "access_token": "client-token",
            "user": {"id": 10, "email": "user@example.com"},
            "client": {"id": 20},
            "is_new": True,
            "password_setup_required": True,
        }

    def onboard_vk_client(self, vk_user_id, bot_token, selected_city_slug=None, full_name=None, source="vk"):
        self.calls.append(
            {
                "vk_user_id": vk_user_id,
                "bot_token": bot_token,
                "selected_city_slug": selected_city_slug,
                "full_name": full_name,
                "source": source,
            }
        )
        return self.payload


class JoinErrorClient:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def onboard_vk_client(self, vk_user_id, bot_token, selected_city_slug=None, full_name=None, source="vk"):
        self.calls.append({"selected_city_slug": selected_city_slug})
        raise self.error


class JoinCityRetryClient:
    def __init__(self):
        self.calls = []

    def onboard_vk_client(self, vk_user_id, bot_token, selected_city_slug=None, full_name=None, source="vk"):
        self.calls.append({"selected_city_slug": selected_city_slug})
        if selected_city_slug:
            raise WebApiError("not_found", status_code=404)
        return {"access_token": "client-token", "user": {"id": 10}, "is_new": True}


def test_join_success_new_user_text_contains_created_and_stores_token():
    reset_user_state(3001)
    client = JoinSuccessClient()

    message = main.handle_join_club(client, 3001, "bot-token", selected_city="Новосибирск")

    assert "Личный кабинет создан" in message
    assert "Пароль в VK не отправляется" in message
    assert "WEB-привязка: активна" not in message
    assert "WEB-кабинет: доступ для бота активен" in message
    assert "Привязать КОД" in message
    assert "код из WEB-кабинета" in message
    assert get_web_client_token(3001) == "client-token"
    assert get_user_state(3001)["web_client_user"]["email"] == "user@example.com"
    assert client.calls[0]["selected_city_slug"] == "novosibirsk"


def test_join_success_existing_user_text_contains_already_created():
    reset_user_state(3002)
    client = JoinSuccessClient(payload={"access_token": "client-token", "user": {"id": 10}, "is_new": False})

    message = main.handle_join_club(client, 3002, "bot-token")

    assert "уже был создан" in message
    assert "WEB-привязка: активна" not in message
    assert "WEB-кабинет" in message
    assert "Привязать КОД" in message
    assert get_web_client_token(3002) == "client-token"


def test_join_401_maps_to_service_auth_ux():
    message = main.handle_join_club(JoinErrorClient(WebApiError("unauthenticated", status_code=401)), 3003, "bot-token")

    assert "Сервисная авторизация бота не настроена" in message


def test_join_web_unavailable_maps_to_unavailable_ux():
    message = main.handle_join_club(JoinErrorClient(WebApiError("web_unavailable")), 3004, "bot-token")

    assert "WEB-сервис временно недоступен" in message


def test_join_city_404_retries_without_city_slug():
    reset_user_state(3005)
    client = JoinCityRetryClient()

    message = main.handle_join_club(client, 3005, "bot-token", selected_city="Новосибирск")

    assert client.calls == [{"selected_city_slug": "novosibirsk"}, {"selected_city_slug": None}]
    assert "Город можно будет выбрать позже" in message
    assert get_web_client_token(3005) == "client-token"
