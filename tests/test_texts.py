import inspect
import json
import sys
import types

import pytest

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
    def __init__(self):
        self.calls = []

    def exchange_vk_link_code(self, vk_user_id, code, bot_token):
        self.calls.append({"vk_user_id": vk_user_id, "code": code, "bot_token": bot_token})
        return {
            "access_token": "client-token",
            "user": {"email": "user@example.com", "role": "member"},
        }


class LinkErrorClient:
    def __init__(self, error):
        self.error = error

    def exchange_vk_link_code(self, vk_user_id, code, bot_token):
        raise self.error


def test_link_success_handler_stores_token_user_and_returns_success_text(caplog):
    reset_user_state(2001)
    client = LinkSuccessClient()

    message = main.handle_vk_link_code(client, 2001, " abc12345 ", "bot-token")

    assert client.calls == [{"vk_user_id": 2001, "code": "ABC12345", "bot_token": "bot-token"}]
    assert get_web_client_token(2001) == "client-token"
    assert get_user_state(2001)["web_client_user"] == {"email": "user@example.com", "role": "member"}
    assert main.restore_web_client_session(client, 2001, "bot-token") is True
    assert "VK привязан к WEB-кабинету" in message
    assert "подписка, партнёры и мои привилегии" in message
    log_text = caplog.text
    assert "client-token" not in log_text
    assert "ABC12345" not in log_text
    assert "abc12345" not in log_text


def test_link_missing_code_returns_instruction_without_web_call():
    reset_user_state(2005)
    client = LinkSuccessClient()

    message = main.handle_vk_link_code(client, 2005, "   ", "bot-token")

    assert client.calls == []
    assert "Привязать КОД" in message
    assert get_web_client_token(2005) is None


@pytest.mark.parametrize(
    "error",
    [
        WebApiError("not_found", status_code=404),
        WebApiError("validation_error", status_code=422, detail="Link code expired"),
        WebApiError("client_error", status_code=400, detail="Invalid link code"),
    ],
)
def test_link_invalid_expired_not_found_maps_to_safe_ux(error):
    message = main.handle_vk_link_code(LinkErrorClient(error), 2002, "ABC12345", "bot-token")

    assert "Код не найден или срок действия истёк" in message
    assert "ABC12345" not in message
    assert "Link code" not in message


def test_link_used_code_maps_to_distinct_ux():
    message = main.handle_vk_link_code(
        LinkErrorClient(WebApiError("validation_error", status_code=400, detail="Link code already used: ABC12345 token=secret")),
        2006,
        "ABC12345",
        "bot-token",
    )

    assert "Этот код уже использован" in message
    assert "ABC12345" not in message
    assert "token=secret" not in message


def test_link_conflict_maps_to_conflict_ux():
    message = main.handle_vk_link_code(
        LinkErrorClient(WebApiError("conflict", status_code=409, detail="vk already linked to another profile")),
        2007,
        "ABC12345",
        "bot-token",
    )

    assert "Этот VK уже привязан к другому кабинету" in message
    assert "another profile" not in message


@pytest.mark.parametrize("error", [WebApiError("unauthenticated", status_code=401), WebApiError("forbidden", status_code=403)])
def test_link_401_403_maps_to_service_auth_ux(error):
    message = main.handle_vk_link_code(LinkErrorClient(error), 2003, "ABC12345", "bot-token")

    assert "Не удалось привязать VK к WEB-кабинету" in message
    assert "401" not in message
    assert "403" not in message


def test_link_web_unavailable_maps_to_unavailable_ux():
    message = main.handle_vk_link_code(LinkErrorClient(WebApiError("web_unavailable")), 2004, "ABC12345", "bot-token")

    assert "WEB-кабинет временно недоступен" in message


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


def test_join_success_new_user_text_contains_login_temporary_password_and_open_button():
    reset_user_state(3001)
    login = "user@example.com"
    temporary_password = "tmp-pass-123"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10, "email": login},
            "client": {"id": 20},
            "is_new": True,
            "login": login,
            "temporary_password": temporary_password,
            "password_hash": "must-not-leak",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3001, "bot-token", selected_city="Новосибирск")

    assert message == (
        "💗 WEB-кабинет создан\n"
        "\n"
        "Вы уже можете открыть bloomclub.ru и посмотреть каталог партнёров.\n"
        "\n"
        "Ваши данные для входа:\n"
        f"Логин: {login}\n"
        f"Пароль: {temporary_password}\n"
        "\n"
        "Сохраните эти данные.\n"
        "\n"
        "Подписка пока не активна до оплаты, поэтому подтверждение привилегий будет доступно после оплаты."
    )
    assert login in message
    assert temporary_password in message
    assert "password_hash" not in message
    assert "must-not-leak" not in message
    actions = _keyboard_actions(keyboard)
    assert actions[0] == {"type": "open_link", "label": "Открыть WEB-кабинет", "link": "https://bloomclub.ru/"}
    assert "Установить новый пароль" not in _keyboard_labels(keyboard)
    assert get_web_client_token(3001) == "client-token"
    assert get_user_state(3001)["web_client_user"]["email"] == login
    assert client.calls[0]["selected_city_slug"] == "novosibirsk"
    assert "temporary_password" not in get_user_state(3001)
    assert "password_hash" not in get_user_state(3001)


def test_join_success_existing_user_text_contains_login_and_setup_button():
    reset_user_state(3002)
    login = "user@example.com"
    setup_url = "https://bloomclub.ru/password/setup?token=one-time-token"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": login,
            "temporary_password": None,
            "password_setup_url": setup_url,
            "password_hash": "must-not-leak",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3002, "bot-token")

    assert message == (
        "💗 WEB-кабинет уже создан\n"
        "\n"
        "Вы можете войти на bloomclub.ru.\n"
        "\n"
        f"Логин: {login}\n"
        "\n"
        "Пароль уже был установлен ранее. Если вы его не помните, установите новый пароль по кнопке ниже."
    )
    assert login in message
    assert "temporary_password" not in message
    assert "password_hash" not in message
    assert "must-not-leak" not in message
    actions = _keyboard_actions(keyboard)
    assert actions[0] == {"type": "open_link", "label": "Открыть WEB-кабинет", "link": "https://bloomclub.ru/"}
    assert actions[1] == {"type": "open_link", "label": "Установить новый пароль", "link": setup_url}
    assert get_web_client_token(3002) == "client-token"
    assert "temporary_password" not in get_user_state(3002)
    assert "password_hash" not in get_user_state(3002)


def test_join_success_existing_user_uses_setup_password_url_alias():
    reset_user_state(3006)
    setup_url = "https://bloomclub.ru/password/setup?token=alias-token"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "user@example.com",
            "temporary_password": None,
            "setup_password_url": setup_url,
        }
    )

    _message, keyboard = main.handle_join_club_result(client, 3006, "bot-token")

    assert {"type": "open_link", "label": "Установить новый пароль", "link": setup_url} in _keyboard_actions(keyboard)


def test_join_success_backward_compatible_missing_temporary_password_is_safe_fallback():
    reset_user_state(3007)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": True,
            "login": "user@example.com",
            "password_hash": "must-not-leak",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3007, "bot-token")

    assert "💗 WEB-кабинет уже создан" in message
    assert "Логин: user@example.com" in message
    assert "Пароль:" not in message
    assert "temporary_password" not in message
    assert "password_hash" not in message
    assert "must-not-leak" not in message
    assert "Открыть WEB-кабинет" in _keyboard_labels(keyboard)
    assert get_web_client_token(3007) == "client-token"


def test_join_success_existing_user_with_invalid_setup_url_has_only_open_button():
    reset_user_state(3008)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "user@example.com",
            "temporary_password": None,
            "password_setup_url": "javascript:alert(1)",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3008, "bot-token")

    assert "Пароль уже был установлен ранее" in message
    assert "javascript:alert" not in message
    labels = _keyboard_labels(keyboard)
    assert "Открыть WEB-кабинет" in labels
    assert "Установить новый пароль" not in labels


def test_join_success_existing_user_with_web_login_url_uses_returned_open_link():
    reset_user_state(3009)
    web_login_url = "https://bloomclub.ru/login?login=user%40example.com"
    setup_url = "https://bloomclub.ru/password/setup?token=one-time-token"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "user@example.com",
            "temporary_password": None,
            "web_login_url": web_login_url,
            "password_setup_url": setup_url,
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3009, "bot-token")

    actions = _keyboard_actions(keyboard)
    assert "💗 WEB-кабинет уже создан" in message
    assert "Логин: user@example.com" in message
    assert actions[0] == {"type": "open_link", "label": "Открыть WEB-кабинет", "link": web_login_url}
    assert actions[1] == {"type": "open_link", "label": "Установить новый пароль", "link": setup_url}


def test_join_success_missing_login_does_not_crash():
    reset_user_state(3014)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": True,
            "temporary_password": "tmp-pass-123",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3014, "bot-token")

    assert "💗 WEB-кабинет создан" in message
    assert "Логин будет доступен в WEB-кабинете" in message
    assert "Пароль: tmp-pass-123" in message
    assert "Открыть WEB-кабинет" in _keyboard_labels(keyboard)


def test_join_success_new_user_with_invalid_web_login_url_uses_safe_default_open_link():
    reset_user_state(3016)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": True,
            "login": "user@example.com",
            "temporary_password": "tmp-pass-123",
            "web_login_url": "javascript:alert(1)",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3016, "bot-token")

    assert "💗 WEB-кабинет создан" in message
    assert "javascript:alert" not in message
    assert _keyboard_actions(keyboard)[0] == {"type": "open_link", "label": "Открыть WEB-кабинет", "link": "https://bloomclub.ru/"}


def test_join_success_existing_user_uses_reset_password_url_alias():
    reset_user_state(3015)
    setup_url = "https://bloomclub.ru/password/reset?token=one-time-token"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "vk_hash@vk.local",
            "temporary_password": None,
            "reset_password_url": setup_url,
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3015, "bot-token")

    assert "Логин: vk_hash@vk.local" in message
    assert {"type": "open_link", "label": "Установить новый пароль", "link": setup_url} in _keyboard_actions(keyboard)


def test_join_success_new_user_ignores_setup_url_and_returns_open_button():
    reset_user_state(3010)
    password_setup_url = "https://bloomclub.ru/password/setup?token=one-time-token"
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": True,
            "login": "user@example.com",
            "temporary_password": "tmp-pass-123",
            "password_setup_url": password_setup_url,
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3010, "bot-token")

    assert "Пароль: tmp-pass-123" in message
    assert password_setup_url not in message
    assert "Установить новый пароль" not in _keyboard_labels(keyboard)
    assert _keyboard_actions(keyboard)[0]["label"] == "Открыть WEB-кабинет"
    assert "password_setup_url" not in get_user_state(3010)


def test_join_success_existing_user_without_setup_url_still_returns_open_button():
    reset_user_state(3011)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "user@example.com",
            "temporary_password": None,
        }
    )

    _message, keyboard = main.handle_join_club_result(client, 3011, "bot-token")

    labels = _keyboard_labels(keyboard)
    assert "Открыть WEB-кабинет" in labels
    assert "Установить новый пароль" not in labels


def test_join_success_with_invalid_setup_url_does_not_return_setup_button():
    reset_user_state(3012)
    client = JoinSuccessClient(
        payload={
            "access_token": "client-token",
            "user": {"id": 10},
            "is_new": False,
            "login": "user@example.com",
            "temporary_password": None,
            "password_setup_url": "ftp://bloomclub.ru/password/setup?token=unused",
        }
    )

    message, keyboard = main.handle_join_club_result(client, 3012, "bot-token")

    assert "Установить новый пароль" not in _keyboard_labels(keyboard)
    assert "token=unused" not in message


def _keyboard_labels(keyboard_json: str) -> list[str]:
    keyboard = json.loads(keyboard_json)
    return [button["action"]["label"] for row in keyboard["buttons"] for button in row]


def _keyboard_actions(keyboard_json: str) -> list[dict]:
    keyboard = json.loads(keyboard_json)
    return [button["action"] for row in keyboard["buttons"] for button in row]


def test_link_code_flow_keyboard_remains_main_menu_without_url_button():
    reset_user_state(3013)

    _message = main.handle_vk_link_code(LinkSuccessClient(), 3013, "ABC12345", "bot-token")
    keyboard = keyboards.get_main_keyboard()

    assert "Задать пароль для WEB-кабинета" not in _keyboard_labels(keyboard)
    assert _keyboard_labels(keyboard) == [
        "💗 Присоединиться к клубу",
        "💗 Подписка",
        "✨ Партнёры и скидки",
        "🎁 Мои привилегии",
        "💳 Оплатить / Продлить",
        "🌸 Выбрать город",
        "❓ Помощь",
    ]


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

class SubscriptionClient:
    def __init__(self, subscription=None, token_payload=None, token_error=None, subscription_error=None):
        self.subscription = subscription or {"has_active_subscription": True, "ends_at": "2026-06-01T00:00:00Z"}
        self.token_payload = token_payload
        self.token_error = token_error
        self.subscription_error = subscription_error
        self.bound_token_calls = []
        self.subscription_calls = []

    def get_vk_bound_token(self, vk_user_id, bot_token):
        self.bound_token_calls.append({"vk_user_id": vk_user_id, "bot_token": bot_token})
        if self.token_error:
            raise self.token_error
        return self.token_payload or {}

    def get_client_subscription(self, token):
        self.subscription_calls.append(token)
        if self.subscription_error:
            raise self.subscription_error
        return self.subscription


class SubscriptionGatewayShouldNotBeCalled:
    def get_subscription(self, vk_user_id):
        raise AssertionError("legacy subscription endpoint must not be called")


def test_format_web_subscription_active_variants():
    assert "Подписка активна до: 01.06.2026" in main.format_web_subscription_message(
        {"has_active_subscription": True, "ends_at": "2026-06-01T00:00:00Z"}
    )
    assert "Подписка активна" in main.format_web_subscription_message({"is_active": True, "expires_at": "2026-07-02"})
    assert "Подписка активна" in main.format_web_subscription_message({"status": "active", "paid_until": "2026-08-03"})
    assert main.is_web_subscription_active({"paid_until": "2099-01-01T00:00:00Z"}) is True


def test_format_web_subscription_inactive_variants():
    assert "Подписка не активна" in main.format_web_subscription_message({"has_active_subscription": False})
    assert "Подписка не активна" in main.format_web_subscription_message({"is_active": False})
    assert "Подписка не активна" in main.format_web_subscription_message({"status": "expired"})
    assert main.is_web_subscription_active({"paid_until": "2000-01-01T00:00:00Z"}) is False


def test_subscription_handler_uses_web_api_when_web_token_present_not_legacy():
    reset_user_state(4001)
    get_user_state(4001)["web_client_token"] = "client-token"
    client = SubscriptionClient(subscription={"has_active_subscription": True, "ends_at": "2026-06-01T00:00:00Z"})

    message = main.handle_subscription_status(client, 4001, "bot-token", gateway=SubscriptionGatewayShouldNotBeCalled())

    assert "Подписка активна до: 01.06.2026" in message
    assert client.bound_token_calls == []
    assert client.subscription_calls == ["client-token"]


def test_subscription_handler_restores_web_token_then_uses_web_api_not_legacy():
    reset_user_state(4002)
    client = SubscriptionClient(
        token_payload={"access_token": "restored-token", "user": {"id": 1}},
        subscription={"status": "active", "paid_until": "2026-06-02T00:00:00Z"},
    )

    message = main.handle_subscription_status(client, 4002, "bot-token", gateway=SubscriptionGatewayShouldNotBeCalled())

    assert "Подписка активна до: 02.06.2026" in message
    assert get_web_client_token(4002) == "restored-token"
    assert client.subscription_calls == ["restored-token"]


def test_subscription_handler_without_web_token_returns_link_instruction_not_legacy():
    reset_user_state(4003)
    client = SubscriptionClient(token_error=WebApiError("not_found", status_code=404))

    message = main.handle_subscription_status(client, 4003, "bot-token", gateway=SubscriptionGatewayShouldNotBeCalled())

    assert "WEB-кабинет" in message
    assert "Привязать КОД" in message
    assert client.subscription_calls == []


def test_subscription_handler_web_api_error_returns_clear_text_not_raw_exception():
    reset_user_state(4004)
    get_user_state(4004)["web_client_token"] = "client-token"
    client = SubscriptionClient(subscription_error=WebApiError("server_error", status_code=500, detail="boom"))

    message = main.handle_subscription_status(client, 4004, "bot-token", gateway=SubscriptionGatewayShouldNotBeCalled())

    assert "Не удалось получить статус подписки" in message
    assert "boom" not in message
    assert "server_error" not in message


class CodesClient:
    def __init__(
        self,
        verifications=None,
        subscription=None,
        token_payload=None,
        token_error=None,
        verifications_error=None,
        subscription_error=None,
    ):
        self.verifications = verifications if verifications is not None else []
        self.subscription = subscription if subscription is not None else {"has_active_subscription": True}
        self.token_payload = token_payload
        self.token_error = token_error
        self.verifications_error = verifications_error
        self.subscription_error = subscription_error
        self.bound_token_calls = []
        self.verification_calls = []
        self.subscription_calls = []

    def get_vk_bound_token(self, vk_user_id, bot_token):
        self.bound_token_calls.append({"vk_user_id": vk_user_id, "bot_token": bot_token})
        if self.token_error:
            raise self.token_error
        return self.token_payload or {}

    def get_client_verifications(self, token, status=None):
        self.verification_calls.append({"token": token, "status": status})
        if self.verifications_error:
            raise self.verifications_error
        return self.verifications

    def get_client_subscription(self, token):
        self.subscription_calls.append(token)
        if self.subscription_error:
            raise self.subscription_error
        return self.subscription


class CodesGatewayShouldNotBeCalled:
    def get_my_codes(self, vk_user_id, status=None):
        raise AssertionError("legacy codes endpoint must not be called")


def test_codes_filter_uses_web_api_when_token_present_not_legacy():
    reset_user_state(5001)
    get_user_state(5001)["web_client_token"] = "client-token"
    client = CodesClient(verifications=[{"code": "WEB-1", "status": "active"}])

    message = main.handle_my_codes_filter(
        client,
        5001,
        "bot-token",
        status="active",
        gateway=CodesGatewayShouldNotBeCalled(),
    )

    assert "WEB-1" in message
    assert "Активна" in message
    assert client.bound_token_calls == []
    assert client.verification_calls == [{"token": "client-token", "status": "active"}]
    assert client.subscription_calls == []


def test_codes_filter_all_status_uses_web_api_without_status_query():
    reset_user_state(5002)
    get_user_state(5002)["web_client_token"] = "client-token"
    client = CodesClient(verifications=[])

    main.handle_my_codes_filter(client, 5002, "bot-token", status="all", gateway=CodesGatewayShouldNotBeCalled())

    assert client.verification_calls == [{"token": "client-token", "status": None}]


def test_active_web_verification_formats_supported_fields():
    reset_user_state(5003)
    get_user_state(5003)["web_client_token"] = "client-token"
    client = CodesClient(
        verifications=[
            {
                "code": "ABC-123",
                "status": "active",
                "created_at": "2026-05-01T10:00:00Z",
                "expires_at": "2026-06-01T10:00:00Z",
                "confirmed_at": "2026-05-03T10:00:00Z",
                "partner": {"name": "Beauty Partner"},
                "offer": {"title": "Скидка на уход"},
            }
        ]
    )

    message = main.handle_my_codes_filter(client, 5003, "bot-token", status="active")

    assert "🎁 Код привилегии: ABC-123" in message
    assert "Партнёр: Beauty Partner" in message
    assert "Предложение: Скидка на уход" in message
    assert "Статус: Активна" in message
    assert "Действует до: 01.06.2026" in message
    assert "Подтверждена: 03.05.2026" in message


def test_empty_web_verifications_with_active_subscription_show_partner_instruction_not_subscribe():
    reset_user_state(5004)
    get_user_state(5004)["web_client_token"] = "client-token"
    client = CodesClient(verifications=[], subscription={"has_active_subscription": True})

    message = main.handle_my_codes_filter(client, 5004, "bot-token", status="active")

    assert message == texts.WEB_PRIVILEGES_EMPTY_WITH_ACTIVE_SUBSCRIPTION_TEXT
    assert "нет полученных привилегий" in message
    assert "Партнёры и скидки" in message
    assert "Получить привилегию" in message
    assert "Оформите подписку" not in message
    assert "оформите подписку" not in message
    assert client.subscription_calls == ["client-token"]
    assert "Данные пока не найдены" not in message


def test_empty_web_verifications_with_inactive_subscription_prompt_payment():
    reset_user_state(5008)
    get_user_state(5008)["web_client_token"] = "client-token"
    client = CodesClient(verifications=[], subscription={"has_active_subscription": False})

    message = main.handle_my_codes_filter(client, 5008, "bot-token", status="active")

    assert message == texts.WEB_PRIVILEGES_REQUIRE_SUBSCRIPTION_TEXT
    assert "нужна активная подписка" in message
    assert "💳 Оплатить / Продлить" in message


def test_empty_web_verifications_subscription_api_error_returns_safe_neutral_text():
    reset_user_state(5009)
    get_user_state(5009)["web_client_token"] = "client-token"
    client = CodesClient(
        verifications=[],
        subscription_error=WebApiError(
            "server_error",
            status_code=500,
            detail="token client-token failed",
        ),
    )

    message = main.handle_my_codes_filter(client, 5009, "bot-token", status="active")

    assert message == texts.WEB_PRIVILEGES_EMPTY_SUBSCRIPTION_UNKNOWN_TEXT
    assert "нет полученных привилегий" in message
    assert "раздел партнёров" in message
    assert "client-token" not in message
    assert "server_error" not in message


@pytest.mark.parametrize("wrapper_key", ["items", "verifications", "results"])
def test_web_verification_response_wrappers_are_supported(wrapper_key):
    reset_user_state(5005)
    get_user_state(5005)["web_client_token"] = "client-token"
    client = CodesClient(verifications={wrapper_key: [{"code": "WRAPPED", "status": "confirmed"}]})

    message = main.handle_my_codes_filter(client, 5005, "bot-token", status="all")

    assert "WRAPPED" in message
    assert "Использована / Подтверждена" in message


def test_codes_filter_without_web_token_returns_link_instruction_not_legacy():
    reset_user_state(5006)
    client = CodesClient(token_error=WebApiError("not_found", status_code=404))

    message = main.handle_my_codes_filter(
        client,
        5006,
        "bot-token",
        status="active",
        gateway=CodesGatewayShouldNotBeCalled(),
    )

    assert "WEB-кабинет" in message
    assert "привяжите VK" in message
    assert "💗 Присоединиться к клубу" in message
    assert client.verification_calls == []


def test_codes_filter_web_api_error_returns_clear_text_without_sensitive_leak():
    reset_user_state(5007)
    get_user_state(5007)["web_client_token"] = "client-token"
    client = CodesClient(
        verifications_error=WebApiError(
            "server_error",
            status_code=500,
            detail="token client-token failed for code SECRET-CODE",
        )
    )

    message = main.handle_my_codes_filter(client, 5007, "bot-token", status="active")

    assert "Не удалось получить список привилегий" in message
    assert "client-token" not in message
    assert "SECRET-CODE" not in message
    assert "server_error" not in message


class PartnersClient:
    def __init__(self, profile=None, partners=None, token_payload=None, token_error=None, profile_error=None, partners_error=None):
        self.profile = profile if profile is not None else {}
        self.partners = partners if partners is not None else []
        self.token_payload = token_payload
        self.token_error = token_error
        self.profile_error = profile_error
        self.partners_error = partners_error
        self.bound_token_calls = []
        self.profile_calls = []
        self.catalog_calls = []

    def get_vk_bound_token(self, vk_user_id, bot_token):
        self.bound_token_calls.append({"vk_user_id": vk_user_id, "bot_token": bot_token})
        if self.token_error:
            raise self.token_error
        return self.token_payload or {}

    def get_client_profile(self, token):
        self.profile_calls.append(token)
        if self.profile_error:
            raise self.profile_error
        return self.profile

    def get_client_catalog_partners(self, token, city_slug=None, category_slug=None, q=None):
        self.catalog_calls.append({"token": token, "city_slug": city_slug, "category_slug": category_slug, "q": q})
        if self.partners_error:
            raise self.partners_error
        return self.partners


class PartnersGatewayShouldNotBeCalled:
    def get_partners(self, category=None):
        raise AssertionError("legacy partners endpoint must not be called")


def test_selected_city_slug_prefers_profile_top_level_nested_then_state_fallback():
    assert main.get_selected_city_slug_from_profile({"selected_city_slug": "novosibirsk"}, {"selected_city": "Череповец"}) == "novosibirsk"
    assert main.get_selected_city_slug_from_profile({"selected_city": {"slug": "cherepovets"}}, {"selected_city": "Новосибирск"}) == "cherepovets"
    assert main.get_selected_city_slug_from_profile({"city_slug": "novosibirsk"}, {"selected_city": "Череповец"}) == "novosibirsk"
    assert main.get_selected_city_slug_from_profile({}, {"selected_city": "Череповец"}) == "cherepovets"


def test_partners_start_restores_web_token_loads_profile_and_category_payload_has_slug():
    reset_user_state(6001)
    get_user_state(6001)["selected_city"] = "Новосибирск"
    client = PartnersClient(token_payload={"access_token": "restored-token"}, profile={"selected_city_slug": "cherepovets"})

    message, keyboard_json = main.handle_partners_start(client, 6001, "bot-token")

    assert message == texts.PARTNERS_INTRO_TEXT
    assert get_user_state(6001)["web_catalog_city_slug"] == "cherepovets"
    assert client.profile_calls == ["restored-token"]
    actions = [button["action"] for button in json.loads(keyboard_json)["buttons"][1:3] for button in button]
    payloads = [json.loads(action["payload"]) for action in actions]
    assert any(payload["category"] == "Красота" and payload["category_slug"] == "beauty" for payload in payloads)


def test_partners_start_without_web_token_returns_link_instruction():
    reset_user_state(6002)
    client = PartnersClient(token_error=WebApiError("not_found", status_code=404))

    message, _keyboard = main.handle_partners_start(client, 6002, "bot-token")

    assert "WEB-кабинет" in message
    assert "💗 Присоединиться к клубу" in message
    assert client.profile_calls == []


def test_category_selected_with_web_token_uses_web_api_not_legacy_and_caches_partners():
    reset_user_state(6003)
    state = get_user_state(6003)
    state["web_client_token"] = "client-token"
    state["web_catalog_city_slug"] = "novosibirsk"
    client = PartnersClient(partners=[{"id": 11, "name": "Beauty Partner", "category_title": "Красота", "city_name": "Новосибирск"}])

    message, keyboard = main.handle_category_selected(
        client,
        6003,
        "bot-token",
        category="Красота",
        category_slug="beauty",
        gateway=PartnersGatewayShouldNotBeCalled(),
    )

    assert "Beauty Partner" in message
    assert client.catalog_calls == [{"token": "client-token", "city_slug": "novosibirsk", "category_slug": "beauty", "q": None}]
    assert get_user_state(6003)["web_catalog_partners_by_id"]["11"]["name"] == "Beauty Partner"
    assert "partner_id" in keyboard


@pytest.mark.parametrize("payload", [
    [{"id": 1, "name": "List Partner"}],
    {"items": [{"id": 2, "name": "Items Partner"}]},
    {"results": [{"id": 3, "name": "Results Partner"}]},
    {"partners": [{"id": 4, "name": "Partners Partner"}]},
])
def test_web_catalog_response_wrappers_are_supported(payload):
    partners = main.extract_web_catalog_partners(payload)

    assert len(partners) == 1
    assert partners[0]["name"].endswith("Partner")


def test_category_selected_uses_nested_profile_city_when_state_city_missing():
    reset_user_state(6004)
    state = get_user_state(6004)
    state["web_client_token"] = "client-token"
    state["web_client_profile"] = {"selected_city": {"slug": "cherepovets"}}
    client = PartnersClient(partners=[])

    message, _keyboard = main.handle_category_selected(client, 6004, "bot-token", category="all", category_slug=None)

    assert client.catalog_calls == [{"token": "client-token", "city_slug": "cherepovets", "category_slug": None, "q": None}]
    assert message == texts.PARTNERS_EMPTY_TEXT
    assert "Данные пока не найдены" not in message


def test_new_onboarded_bound_active_user_opens_partners_without_generic_error():
    reset_user_state(6010)
    state = get_user_state(6010)
    state["web_client_token"] = "client-token"
    state["web_link_status"] = "active"
    client = PartnersClient(profile={"selected_city_slug": "novosibirsk"})

    message, keyboard_json = main.handle_partners_start(client, 6010, "bot-token")

    assert message == texts.PARTNERS_INTRO_TEXT
    assert "Произошла ошибка" not in message
    assert client.profile_calls == ["client-token"]
    assert get_user_state(6010)["web_catalog_city_slug"] == "novosibirsk"
    assert "category_selected" in keyboard_json


def test_empty_web_catalog_returns_city_empty_state_message():
    reset_user_state(6011)
    state = get_user_state(6011)
    state["web_client_token"] = "client-token"
    state["web_catalog_city_slug"] = "novosibirsk"
    client = PartnersClient(partners={"data": {"items": []}})

    message, _keyboard = main.handle_category_selected(client, 6011, "bot-token", category="all", category_slug=None)

    assert message == "Партнёры в вашем городе пока не найдены. Попробуйте выбрать другой город или загляните позже."
    assert "Произошла ошибка" not in message


def test_missing_city_for_web_catalog_prompts_city_selection_without_catalog_call():
    reset_user_state(6012)
    get_user_state(6012)["web_client_token"] = "client-token"
    client = PartnersClient(partners=[{"id": 1, "name": "Partner"}])

    message, keyboard_json = main.handle_category_selected(client, 6012, "bot-token", category="all", category_slug=None)

    assert message == texts.PARTNERS_CITY_REQUIRED_TEXT
    assert client.catalog_calls == []
    assert keyboards.BUTTON_CITY.split(maxsplit=1)[-1] not in message
    assert "city_selected" in keyboard_json


@pytest.mark.parametrize("payload", [None, "not-json", {"data": None}, {"data": {"items": None}}, {"items": [None, "bad"]}])
def test_invalid_web_catalog_payload_returns_safe_empty_state(payload):
    reset_user_state(6013)
    state = get_user_state(6013)
    state["web_client_token"] = "client-token"
    state["web_catalog_city_slug"] = "novosibirsk"
    client = PartnersClient(partners=payload)

    message, _keyboard = main.handle_category_selected(client, 6013, "bot-token", category="all", category_slug=None)

    assert message == texts.PARTNERS_EMPTY_TEXT
    assert "Произошла ошибка" not in message


def test_catalog_data_wrapper_is_supported():
    partners = main.extract_web_catalog_partners({"data": {"items": [{"id": 5, "name": "Data Partner"}]}})

    assert partners == [{"id": 5, "name": "Data Partner"}]


def test_partners_start_invalid_profile_payload_is_safe_city_prompt():
    reset_user_state(6014)
    get_user_state(6014)["web_client_token"] = "client-token"
    client = PartnersClient(profile=["unexpected"])

    message, keyboard_json = main.handle_partners_start(client, 6014, "bot-token")

    assert message == texts.PARTNERS_CITY_REQUIRED_TEXT
    assert "Произошла ошибка" not in message
    assert "city_selected" in keyboard_json


def test_category_selected_web_api_error_returns_safe_text_without_raw_exception():
    reset_user_state(6005)
    state = get_user_state(6005)
    state["web_client_token"] = "client-token"
    state["web_catalog_city_slug"] = "novosibirsk"
    client = PartnersClient(partners_error=WebApiError("server_error", status_code=500, detail="token client-token SECRET"))

    message, _keyboard = main.handle_category_selected(client, 6005, "bot-token", category="Красота", category_slug="beauty")

    assert "Не удалось получить партнёров из WEB-кабинета" in message
    assert "client-token" not in message
    assert "SECRET" not in message
    assert "server_error" not in message


def test_unknown_category_slug_does_not_crash_or_call_catalog():
    reset_user_state(6006)
    get_user_state(6006)["web_client_token"] = "client-token"
    client = PartnersClient()

    message, _keyboard = main.handle_category_selected(client, 6006, "bot-token", category="Неизвестная категория", category_slug=None)

    assert "Не удалось определить категорию" in message
    assert client.catalog_calls == []


class WebPartnerFlowClient:
    def __init__(self, token_payload=None, offers=None, verification=None, token_error=None, offers_error=None, verification_error=None):
        self.token_payload = token_payload
        self.offers = offers if offers is not None else []
        self.verification = verification if verification is not None else {"code": "WEB-CODE", "status": "active"}
        self.token_error = token_error
        self.offers_error = offers_error
        self.verification_error = verification_error
        self.bound_token_calls = []
        self.offers_calls = []
        self.verification_calls = []

    def get_vk_bound_token(self, vk_user_id, bot_token):
        self.bound_token_calls.append({"vk_user_id": vk_user_id, "bot_token": bot_token})
        if self.token_error:
            raise self.token_error
        return self.token_payload or {}

    def get_client_partner_offers(self, token, partner_id):
        self.offers_calls.append({"token": token, "partner_id": partner_id})
        if self.offers_error:
            raise self.offers_error
        return self.offers

    def create_client_partner_verification(self, token, partner_id, offer_id=None):
        self.verification_calls.append({"token": token, "partner_id": partner_id, "offer_id": offer_id})
        if self.verification_error:
            raise self.verification_error
        return self.verification


class LegacyServicesGatewayShouldNotBeCalled:
    def get_partner_services(self, partner_id):
        raise AssertionError("legacy services endpoint must not be called")

    def request_discount_code(self, vk_user_id, partner_id, service_id):
        raise AssertionError("legacy discount code endpoint must not be called")


def test_web_partner_selected_missing_partner_id_returns_safe_text():
    reset_user_state(7101)
    get_user_state(7101)["web_client_token"] = "client-token"
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_partner_selected(client, 7101, "bot-token", " ")

    assert message == main.PARTNER_PAYLOAD_INVALID_TEXT
    assert client.offers_calls == []


def test_web_partner_selected_stale_cache_returns_stale_text_without_legacy_call():
    reset_user_state(7102)
    state = get_user_state(7102)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {}
    client = WebPartnerFlowClient()
    legacy = LegacyServicesGatewayShouldNotBeCalled()

    message, _keyboard = main.handle_web_partner_selected(client, 7102, "bot-token", 11)

    assert message == main.PARTNER_CACHE_STALE_TEXT
    assert client.offers_calls == []
    assert legacy is not None


def test_web_partner_selected_non_int_id_returns_safe_text_without_web_api_call():
    reset_user_state(7103)
    state = get_user_state(7103)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"uuid-11": {"id": "uuid-11", "name": "UUID Partner"}}
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_partner_selected(client, 7103, "bot-token", "uuid-11")

    assert message == main.PARTNER_PAYLOAD_INVALID_TEXT
    assert client.offers_calls == []


def test_web_offer_selected_missing_offer_id_returns_safe_text():
    reset_user_state(7104)
    state = get_user_state(7104)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_offer_selected(client, 7104, "bot-token", 11, None, offer_required=True)

    assert message == main.OFFER_PAYLOAD_INVALID_TEXT
    assert client.verification_calls == []


def test_web_offer_selected_stale_offer_returns_stale_text():
    reset_user_state(7105)
    state = get_user_state(7105)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {}
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_offer_selected(client, 7105, "bot-token", 11, 5, offer_required=True)

    assert message == main.OFFER_CACHE_STALE_TEXT
    assert client.verification_calls == []


@pytest.mark.parametrize(
    ("partner_id", "offer_id", "expected"),
    [
        ("uuid-partner", 5, main.PARTNER_PAYLOAD_INVALID_TEXT),
        (11, "uuid-offer", main.OFFER_PAYLOAD_INVALID_TEXT),
    ],
)
def test_web_offer_selected_non_int_ids_return_safe_text_without_verify_call(partner_id, offer_id, expected):
    reset_user_state(7106)
    state = get_user_state(7106)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {str(partner_id): {"id": partner_id, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {str(offer_id): {"id": offer_id, "partner_id": partner_id, "title": "Offer"}}
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_offer_selected(client, 7106, "bot-token", partner_id, offer_id, offer_required=True)

    assert message == expected
    assert client.verification_calls == []


@pytest.mark.parametrize(
    ("partner_id", "partners_cache", "expected"),
    [
        (None, {"11": {"id": 11}}, main.PARTNER_PAYLOAD_INVALID_TEXT),
        (11, {}, main.PARTNER_CACHE_STALE_TEXT),
        ("uuid-partner", {"uuid-partner": {"id": "uuid-partner"}}, main.PARTNER_PAYLOAD_INVALID_TEXT),
    ],
)
def test_web_get_privilege_missing_stale_non_int_partner_returns_safe_text(partner_id, partners_cache, expected):
    reset_user_state(7107)
    state = get_user_state(7107)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = partners_cache
    client = WebPartnerFlowClient()

    message, _keyboard = main.handle_web_offer_selected(client, 7107, "bot-token", partner_id, None)

    assert message == expected
    assert client.verification_calls == []


def test_legacy_partner_selected_invalid_id_helpers_no_longer_raise_generic_exception():
    assert main.safe_int_id("not-an-int") is None
    assert main.normalize_payload_id("  legacy-id  ") == "legacy-id"


def test_web_partner_selected_loads_offers_and_caches_without_legacy_services():
    reset_user_state(7001)
    state = get_user_state(7001)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    client = WebPartnerFlowClient(offers={"offers": [{"id": 5, "title": "Скидка на уход"}]})

    message, keyboard_json = main.handle_web_partner_selected(client, 7001, "bot-token", 11)

    assert "Beauty Partner" in message
    assert "Выберите предложение" in message
    assert client.offers_calls == [{"token": "client-token", "partner_id": 11}]
    assert get_user_state(7001)["web_partner_offers_by_partner_id"]["11"][0]["title"] == "Скидка на уход"
    payloads = [json.loads(button["action"]["payload"]) for row in json.loads(keyboard_json)["buttons"] for button in row]
    assert {"action": "web_offer_selected", "partner_id": 11, "offer_id": 5} in payloads


def test_web_partner_offer_response_wrappers_are_supported():
    for payload in ([{"id": 1}], {"items": [{"id": 2}]}, {"offers": [{"id": 3}]}, {"results": [{"id": 4}]}):
        assert len(main.extract_web_partner_offers(payload)) == 1


def test_web_offer_selected_calls_verify_endpoint_and_formats_code():
    reset_user_state(7002)
    state = get_user_state(7002)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {"5": {"id": 5, "partner_id": 11, "title": "Скидка на уход"}}
    client = WebPartnerFlowClient(verification={"code": "ABC-777", "status": "active", "expires_at": "2026-06-01T10:00:00Z"})

    message, _keyboard = main.handle_web_offer_selected(client, 7002, "bot-token", 11, 5)

    assert client.verification_calls == [{"token": "client-token", "partner_id": 11, "offer_id": 5}]
    assert "🎁 Код привилегии: ABC-777" in message
    assert "Партнёр: Beauty Partner" in message
    assert "Предложение: Скидка на уход" in message
    assert "Действует до: 01.06.2026" in message
    assert "Покажите этот код партнёру" in message


@pytest.mark.parametrize("wrapper_key", ["verification", "session", "item"])
def test_web_created_verification_wrappers_are_supported(wrapper_key):
    message = main.format_web_created_verification_message({wrapper_key: {"code": "WRAP-1", "partner_name": "Partner", "offer_title": "Offer"}})

    assert "WRAP-1" in message
    assert "Partner" in message
    assert "Offer" in message


def test_web_offer_without_token_returns_link_required_text():
    reset_user_state(7003)
    client = WebPartnerFlowClient(token_error=WebApiError("not_found", status_code=404))

    message, _keyboard = main.handle_web_offer_selected(client, 7003, "bot-token", 11, 5)

    assert "WEB-кабинет" in message
    assert "💗 Присоединиться к клубу" in message
    assert client.verification_calls == []


def test_web_verify_no_subscription_returns_pay_instruction():
    reset_user_state(7004)
    state = get_user_state(7004)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {"5": {"id": 5, "partner_id": 11, "title": "Скидка на уход"}}
    client = WebPartnerFlowClient(verification_error=WebApiError("forbidden", status_code=403, detail="no_subscription"))

    message, keyboard_json = main.handle_web_offer_selected(client, 7004, "bot-token", 11, 5)

    assert "Для получения привилегии нужна активная подписка" in message
    assert "Оплатить / Продлить" in keyboard_json


def test_web_verify_404_returns_unavailable_text():
    reset_user_state(7005)
    state = get_user_state(7005)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {"5": {"id": 5, "partner_id": 11, "title": "Скидка на уход"}}
    client = WebPartnerFlowClient(verification_error=WebApiError("not_found", status_code=404))

    message, _keyboard = main.handle_web_offer_selected(client, 7005, "bot-token", 11, 5)

    assert message == "Партнёр или предложение недоступны."


def test_web_verify_safe_error_text_does_not_leak_exception_token_or_code():
    reset_user_state(7006)
    state = get_user_state(7006)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    state["web_partner_offers_by_id"] = {"5": {"id": 5, "partner_id": 11, "title": "Скидка на уход"}}
    client = WebPartnerFlowClient(verification_error=WebApiError("server_error", status_code=500, detail="token client-token code SECRET-CODE"))

    message, _keyboard = main.handle_web_offer_selected(client, 7006, "bot-token", 11, 5)

    assert "Не удалось получить привилегию" in message
    assert "client-token" not in message
    assert "SECRET-CODE" not in message
    assert "server_error" not in message


def test_web_get_privilege_without_offer_calls_verify_with_empty_offer_id():
    reset_user_state(7007)
    state = get_user_state(7007)
    state["web_client_token"] = "client-token"
    state["web_catalog_partners_by_id"] = {"11": {"id": 11, "name": "Beauty Partner"}}
    client = WebPartnerFlowClient(verification={"code": "NO-OFFER", "status": "active"})

    message, _keyboard = main.handle_web_offer_selected(client, 7007, "bot-token", 11, None)

    assert client.verification_calls == [{"token": "client-token", "partner_id": 11, "offer_id": None}]
    assert "NO-OFFER" in message


class PaymentGatewayShouldNotBeCalled:
    def create_payment_request(self, vk_user_id):
        raise AssertionError("legacy payment endpoint must not be called")

    def mark_payment_paid(self, vk_user_id, payment_request_id=None):
        raise AssertionError("legacy payment paid endpoint must not be called")


class PaymentWebClient:
    def __init__(self, token_payload=None, token_error=None, create_error=None, mark_error=None, requests_error=None, requests=None):
        self.token_payload = token_payload
        self.token_error = token_error
        self.create_error = create_error
        self.mark_error = mark_error
        self.requests_error = requests_error
        self.requests = requests if requests is not None else []
        self.bound_token_calls = []
        self.create_calls = []
        self.mark_calls = []
        self.list_calls = []

    def get_vk_bound_token(self, vk_user_id, bot_token):
        self.bound_token_calls.append({"vk_user_id": vk_user_id, "bot_token": bot_token})
        if self.token_error:
            raise self.token_error
        return self.token_payload or {}

    def create_client_payment_request(self, token, amount=None, source="vk", comment=None):
        self.create_calls.append({"token": token, "amount": amount, "source": source, "comment": comment})
        if self.create_error:
            raise self.create_error
        return {"id": 101, "amount": main.SUBSCRIPTION_PRICE_RUB, "status": "pending", "created_at": "2026-05-17T10:00:00Z"}

    def mark_client_payment_paid(self, token, payment_request_id, comment=None):
        self.mark_calls.append({"token": token, "payment_request_id": payment_request_id, "comment": comment})
        if self.mark_error:
            raise self.mark_error
        return {"id": payment_request_id, "amount": main.SUBSCRIPTION_PRICE_RUB, "status": "paid", "created_at": "2026-05-17T10:00:00Z"}

    def get_client_payment_requests(self, token):
        self.list_calls.append(token)
        if self.requests_error:
            raise self.requests_error
        return self.requests


def test_format_web_payment_request_maps_statuses_and_fields():
    message = main.format_web_payment_request(
        {
            "id": 7,
            "amount": 1500,
            "status": "approved",
            "created_at": "2026-05-17T10:00:00Z",
            "comment": "manual",
            "access_until": "2026-06-17T10:00:00Z",
        }
    )

    assert "ID заявки: 7" in message
    assert "Сумма: 1500" in message
    assert "Статус: Подтверждено" in message
    assert "Комментарий: manual" in message
    assert "Доступ до:" in message
    assert main.format_web_payment_status("pending") == "Ожидает оплаты"
    assert main.format_web_payment_status("paid") == "Оплачено, ожидает проверки"
    assert main.format_web_payment_status("rejected") == "Отклонено"


def test_format_web_payment_request_with_missing_amount_shows_subscription_price():
    message = main.format_web_payment_request({"id": 8, "status": "pending"})

    assert "Сумма: 349 ₽" in message


def test_format_web_payment_request_with_zero_amount_shows_subscription_price():
    for amount in (None, 0, "0", "0.00"):
        message = main.format_web_payment_request({"id": 8, "amount": amount, "status": "pending"})

        assert "Сумма: 349 ₽" in message
        assert "Сумма: 0" not in message


def test_payment_button_with_web_token_creates_web_request_not_legacy():
    reset_user_state(7001)
    get_user_state(7001)["web_client_token"] = "client-token"
    client = PaymentWebClient()

    message, keyboard = main.handle_web_payment_request(client, 7001, "bot-token")

    assert "Заявка на оплату создана" in message
    assert "ID заявки: 101" in message
    assert "349 ₽" in message
    assert "Ожидает оплаты" in message
    assert "✅ Я оплатил" in message
    assert "администратор проверит" in message.lower()
    assert get_user_state(7001)["last_payment_request_id"] == 101
    assert client.create_calls == [
        {"token": "client-token", "amount": main.SUBSCRIPTION_PRICE_RUB, "source": "vk", "comment": None}
    ]
    assert "payment_paid" in keyboard


def test_payment_button_without_web_token_returns_link_required_text():
    reset_user_state(7002)
    client = PaymentWebClient(token_error=WebApiError("not_found", status_code=404))

    message, _keyboard = main.handle_web_payment_request(client, 7002, "bot-token")

    assert "WEB-кабинет" in message
    assert "Привязать КОД" in message
    assert "Присоединиться к клубу" in message
    assert client.create_calls == []


def test_payment_paid_marks_stored_web_request_paid():
    reset_user_state(7003)
    state = get_user_state(7003)
    state["web_client_token"] = "client-token"
    state["last_payment_request_id"] = 101
    client = PaymentWebClient()

    message = main.handle_web_payment_paid(client, 7003, "bot-token")

    assert "отметили заявку как оплаченную" in message
    assert "Оплачено, ожидает проверки" in message
    assert "проверит оплату вручную" in message
    assert client.mark_calls == [
        {"token": "client-token", "payment_request_id": 101, "comment": "Клиент нажал Я оплатил в VK"}
    ]


def test_payment_paid_without_stored_id_uses_latest_pending_request():
    reset_user_state(7004)
    state = get_user_state(7004)
    state["web_client_token"] = "client-token"
    client = PaymentWebClient(requests=[{"id": 202, "status": "pending", "amount": 1500}])

    message = main.handle_web_payment_paid(client, 7004, "bot-token")

    assert "Оплачено, ожидает проверки" in message
    assert get_user_state(7004)["last_payment_request_id"] == 202
    assert client.list_calls == ["client-token"]
    assert client.mark_calls[0]["payment_request_id"] == 202


def test_payment_paid_without_any_request_asks_to_create_payment():
    reset_user_state(7005)
    state = get_user_state(7005)
    state["web_client_token"] = "client-token"
    client = PaymentWebClient(requests=[])

    message = main.handle_web_payment_paid(client, 7005, "bot-token")

    assert message == texts.PAYMENT_REQUEST_NOT_FOUND_TEXT
    assert client.mark_calls == []


def test_web_payment_errors_return_safe_texts_without_raw_detail():
    reset_user_state(7006)
    state = get_user_state(7006)
    state["web_client_token"] = "client-token"
    client = PaymentWebClient(create_error=WebApiError("server_error", status_code=500, detail="raw boom"))

    message, _keyboard = main.handle_web_payment_request(client, 7006, "bot-token")

    assert "Не удалось обработать оплату" in message
    assert "raw boom" not in message
    assert "server_error" not in message

    assert "WEB-кабинет" in main.map_web_payment_error_to_text(WebApiError("unauthenticated", status_code=401))
    assert main.map_web_payment_error_to_text(WebApiError("not_found", status_code=404)) == texts.PAYMENT_WEB_NOT_FOUND_TEXT
