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
