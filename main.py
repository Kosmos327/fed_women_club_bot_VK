import json
import logging
import random
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from dotenv import load_dotenv
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError

from city_mapping import get_web_known_city_slug
from config import load_config
from diagnostics import format_debug_status, format_health_status
from keyboards import (
    BUTTON_CITY,
    BUTTON_HELP,
    BUTTON_JOIN_CLUB,
    BUTTON_MAIN_MENU,
    BUTTON_MY_CODES,
    BUTTON_PARTNERS,
    BUTTON_PAY,
    BUTTON_SUBSCRIPTION,
    WOMEN_CATEGORIES,
    get_admin_keyboard,
    get_backend_unavailable_keyboard,
    get_categories_keyboard,
    get_city_keyboard,
    get_city_selected_keyboard,
    get_codes_filter_keyboard,
    get_main_keyboard,
    get_nav_keyboard,
    get_no_subscription_keyboard,
    get_partner_actions_keyboard,
    get_partners_keyboard,
    get_payment_request_keyboard,
    get_service_actions_keyboard,
    get_service_search_results_keyboard,
    get_services_keyboard,
    get_verify_error_keyboard,
    get_verify_success_keyboard,
)
from routing import parse_code_command, parse_link_code_command, parse_partner_command, parse_service_command, parse_verify_partner_command
from services.backend_gateway import BackendApiError, BackendGateway
from services.web_api_client import WebApiClient, WebApiError
from state import USER_STATE, clear_user_flow_state, get_user_state, get_web_client_token, set_web_client_session
from texts import (
    BACKEND_UNAVAILABLE_TEXT,
    FALLBACK_TEXT,
    HELP_TEXT,
    JOIN_CLUB_GENERIC_ERROR_TEXT,
    JOIN_CLUB_SERVICE_AUTH_ERROR_TEXT,
    JOIN_CLUB_WEB_UNAVAILABLE_TEXT,
    MAIN_MENU_TEXT,
    MY_PRIVILEGES_EMPTY_TEXT,
    MY_PRIVILEGES_FILTER_TEXT,
    NO_SUBSCRIPTION_TEXT,
    PARTNERS_FOUND_TEXT,
    PARTNERS_INTRO_TEXT,
    PAYMENT_RECEIPT_RECEIVED_TEXT,
    PAYMENT_RECEIPT_REQUEST_TEXT,
    PAYMENT_REQUEST_NOT_FOUND_TEXT,
    PRIVILEGE_LIMIT_REACHED_TEXT,
    SERVICE_SEARCH_EMPTY_TEXT,
    SERVICE_SEARCH_PROMPT_TEXT,
    SERVICE_SEARCH_RESULTS_TEXT,
    SERVICES_INTRO_TEXT,
    SUBSCRIPTION_ACTIVE_TEXT,
    SUBSCRIPTION_INACTIVE_TEXT,
    VERIFY_PARTNER_NOT_FOUND_TEXT,
    VERIFY_PRIVILEGE_FAILED_TEXT,
    VK_LINK_CODE_INVALID_TEXT,
    VK_LINK_CODE_NOT_FOUND_TEXT,
    VK_LINK_SERVICE_AUTH_ERROR_TEXT,
    VK_LINK_STATUS_ACTIVE_TEXT,
    VK_LINK_STATUS_INACTIVE_TEXT,
    VK_LINK_WEB_UNAVAILABLE_TEXT,
    WELCOME_TEXT,
)
from vk_attachments import extract_attachment_url

logger = logging.getLogger("vk_bot")
logging.basicConfig(level=logging.INFO)


def normalize_text(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def send_message(vk_api, peer_id: int, text: str, keyboard: Optional[str] = None) -> None:
    vk_api.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=random.randint(1, 2_147_483_647),
        keyboard=keyboard or get_main_keyboard(),
    )


def extract_action(message: dict) -> tuple[str | None, dict]:
    raw_payload = message.get("payload")
    if not raw_payload:
        return None, {}
    try:
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
    except json.JSONDecodeError:
        return None, {}
    if not isinstance(payload, dict):
        return None, {}
    return payload.get("action"), payload


def _is_filled(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "—", "None"}
    return True


def format_user_date(value: str | None) -> str:
    if not value:
        return "—"
    raw_value = value.strip()
    if not raw_value:
        return "—"
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return raw_value or "—"
    return parsed.strftime("%d.%m.%Y")


def format_money(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    normalized = f"{amount:,.2f}".replace(",", " ").replace(".00", "")
    return f"{normalized} ₽"


def format_discount_percent(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    formatted = format(amount.normalize(), "f")
    return f"{formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted}%"


def get_partner_address(partner_or_service_context: dict) -> str | None:
    partner = partner_or_service_context.get("partner")
    if isinstance(partner, dict) and _is_filled(partner.get("address")):
        return str(partner.get("address")).strip()
    for key in ("partner_address", "address"):
        if _is_filled(partner_or_service_context.get(key)):
            return str(partner_or_service_context.get(key)).strip()
    return None


def format_partner_card(partner: dict) -> str:
    lines = [f"{partner.get('name') or 'Партнёр'}"]
    if _is_filled(partner.get("description")):
        lines.extend(["", str(partner.get("description")).strip()])
    if _is_filled(partner.get("category")):
        lines.append(f"Категория: {partner.get('category')}")
    if _is_filled(partner.get("address")):
        lines.append(f"Адрес: {partner.get('address')}")
    if _is_filled(partner.get("phone")):
        lines.append(f"Телефон: {partner.get('phone')}")
    website = partner.get("website_url") or partner.get("website")
    if _is_filled(website):
        lines.append(f"Сайт: {website}")
    return "\n".join(lines)


def format_service_card(service: dict, partner_name: Optional[str] = None, partner_address: str | None = None) -> str:
    lines = [f"{service.get('title') or 'Услуга'}"]
    if _is_filled(partner_name):
        lines.extend(["", f"Партнёр: {partner_name}"])
    if _is_filled(partner_address):
        lines.append(f"Адрес: {partner_address}")
    if _is_filled(service.get("description")):
        lines.extend(["", str(service.get("description")).strip()])
    if _is_filled(service.get("base_price")):
        lines.append(f"Обычная цена: {format_money(service.get('base_price'))}")
    final_price = service.get("final_price") or service.get("discounted_price")
    if _is_filled(final_price):
        lines.append(f"Цена со скидкой: {format_money(final_price)}")
    if _is_filled(service.get("discount_text")):
        lines.append(f"Скидка: {service.get('discount_text')}")
    elif _is_filled(service.get("discount_percent")):
        lines.append(f"Скидка: {format_discount_percent(service.get('discount_percent'))}")
    return "\n".join(lines)


def format_code_item(code_data: dict) -> str:
    lines = [
        f"Привилегия: {code_data.get('code') or '—'}",
        f"Партнёр: {code_data.get('partner_name') or '—'}",
        f"Статус: {code_data.get('status') or '—'}",
        f"Выдана: {format_user_date(code_data.get('created_at'))}",
        f"Действует до: {format_user_date(code_data.get('expires_at'))}",
    ]
    service_name = code_data.get("service_title") or code_data.get("service_name")
    if _is_filled(service_name):
        lines.insert(2, f"Предложение: {service_name}")
    return "\n".join(lines)


def format_city_selected_message(city: str) -> str:
    return f"Город выбран: {city}. Теперь покажем партнёров и предложения рядом."


def format_payment_request_message(payment: dict) -> str:
    amount = payment.get("amount") or "—"
    instructions = (payment.get("payment_instructions") or "").strip()
    parts = [f"Сумма: {amount}"]
    if instructions:
        parts.append(instructions)
    parts.append("После оплаты нажмите «✅ Я оплатил» и отправьте скрин оплаты.")
    return "\n".join(parts)


def format_backend_error_message(exc: BackendApiError) -> str:
    code = (exc.code or "").strip().lower()
    status_code = exc.status_code

    if code == "no_subscription":
        return NO_SUBSCRIPTION_TEXT
    if code == "payment_request_not_found":
        return PAYMENT_REQUEST_NOT_FOUND_TEXT
    if code == "discount_code_limit_reached":
        return PRIVILEGE_LIMIT_REACHED_TEXT
    if code == "backend_unavailable":
        return BACKEND_UNAVAILABLE_TEXT
    if status_code in {401, 403} or code in {"auth", "forbidden", "unauthorized", "unauthenticated"}:
        return "Не удалось подтвердить доступ к сервису. Попробуйте позже или откройте главное меню."
    if status_code == 404 or code == "not_found":
        return "Данные пока не найдены. Попробуйте обновить действие или откройте главное меню."
    if status_code == 422 or code in {"validation", "validation_error"}:
        return "Не удалось обработать запрос. Попробуйте открыть главное меню и повторить действие."
    if (status_code is not None and status_code >= 500) or code in {"server_error", "internal_error"}:
        return "На стороне сервиса произошла ошибка. Мы уже можем проверить её по логам. Попробуйте позже."
    return BACKEND_UNAVAILABLE_TEXT


def handle_payment_paid(gateway: BackendGateway, vk_user_id: int) -> str:
    state = get_user_state(vk_user_id)
    gateway.mark_payment_paid(vk_user_id, payment_request_id=state.get("last_payment_request_id"))
    state["awaiting_payment_receipt"] = True
    return PAYMENT_RECEIPT_REQUEST_TEXT


def handle_verify_partner(gateway: BackendGateway, vk_user_id: int | str, partner_id: int) -> tuple[str, str]:
    try:
        response = gateway.verify_partner(vk_user_id, partner_id)
    except BackendApiError as exc:
        if exc.code == "no_subscription":
            return NO_SUBSCRIPTION_TEXT, get_no_subscription_keyboard()
        if exc.code == "backend_unavailable":
            return BACKEND_UNAVAILABLE_TEXT, get_backend_unavailable_keyboard()
        return VERIFY_PARTNER_NOT_FOUND_TEXT, get_verify_error_keyboard()
    if response.get("ok") is True:
        expires_at = response.get("expires_at") or response.get("expires") or "—"
        return (
            "✅ Привилегия подтверждена\n\n"
            f"Партнёр: {response.get('partner_name') or '—'}\n"
            f"Код подтверждения: {response.get('dynamic_code') or '—'}\n"
            "Действует 5 минут\n"
            f"Действует до: {expires_at}\n\n"
            "Покажите этот экран сотруднику партнёра.",
            get_verify_success_keyboard(),
        )
    return VERIFY_PRIVILEGE_FAILED_TEXT, get_verify_error_keyboard()



def _extract_web_token(payload: dict) -> str | None:
    for key in ("access_token", "token", "client_token"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _extract_web_user(payload: dict) -> dict:
    for key in ("user", "client", "client_user"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def format_link_success(user: dict | None) -> str:
    user = user or {}
    lines = ["VK привязан к личному кабинету"]
    contact = user.get("email") or user.get("phone")
    if contact:
        lines.append(f"Контакт: {contact}")
    role = user.get("role")
    if role:
        lines.append(f"Роль: {role}")
    lines.extend(["", "Теперь можно использовать WEB-привилегии в боте."])
    return "\n".join(lines)


def map_web_api_error_to_link_text(error: WebApiError) -> str:
    if error.code == "unauthenticated" or error.status_code == 401:
        return VK_LINK_SERVICE_AUTH_ERROR_TEXT
    if error.code == "not_found" or error.status_code == 404:
        return VK_LINK_CODE_NOT_FOUND_TEXT
    if error.code in {"client_error", "validation_error"} or error.status_code in {400, 422}:
        return VK_LINK_CODE_INVALID_TEXT
    return VK_LINK_WEB_UNAVAILABLE_TEXT


def handle_vk_link_code(web_client: WebApiClient, vk_user_id: int | str, code: str, bot_token: str) -> str:
    try:
        payload = web_client.exchange_vk_link_code(vk_user_id, code, bot_token)
    except WebApiError as exc:
        return map_web_api_error_to_link_text(exc)
    if not isinstance(payload, dict):
        return VK_LINK_WEB_UNAVAILABLE_TEXT
    token = _extract_web_token(payload)
    if not token:
        return VK_LINK_WEB_UNAVAILABLE_TEXT
    user = _extract_web_user(payload)
    set_web_client_session(vk_user_id, token, user, linked_at=datetime.now(timezone.utc).isoformat())
    return format_link_success(user)


def restore_web_client_session(web_client: WebApiClient, vk_user_id: int | str, bot_token: str) -> bool:
    if get_web_client_token(vk_user_id):
        return True
    try:
        payload = web_client.get_vk_bound_token(vk_user_id, bot_token)
    except WebApiError:
        return False
    if not isinstance(payload, dict):
        return False
    token = _extract_web_token(payload)
    if not token:
        return False
    set_web_client_session(vk_user_id, token, _extract_web_user(payload), linked_at=datetime.now(timezone.utc).isoformat())
    return True


def format_web_link_status(is_linked: bool) -> str:
    return VK_LINK_STATUS_ACTIVE_TEXT if is_linked else VK_LINK_STATUS_INACTIVE_TEXT


def extract_web_session_from_onboard_response(response: dict) -> tuple[str | None, dict]:
    token = _extract_web_token(response)
    user = _extract_web_user(response)
    client = response.get("client")
    if isinstance(client, dict) and client:
        user = {**client, **user}
    return token, user


def build_join_club_success_text(response: dict, city_retry_without_slug: bool = False) -> str:
    if response.get("is_new") is True:
        first_line = "Личный кабинет создан"
    else:
        first_line = "Личный кабинет уже был создан, доступ обновлён"
    lines = [
        first_line,
        "",
        "Вы уже можете открыть bloomclub.ru и посмотреть каталог партнёров.",
        "Подписка пока не активна до оплаты, поэтому подтверждение привилегий будет доступно после оплаты.",
        "Пароль в VK не отправляется. Вход по паролю в WEB будет подключён через безопасную установку пароля.",
        "WEB-кабинет: доступ для бота активен.",
        "Явная VK-привязка: через код из WEB-кабинета. "
        "Создайте код в WEB-кабинете и отправьте сюда: Привязать КОД",
    ]
    if city_retry_without_slug:
        lines.append("Город можно будет выбрать позже в личном кабинете.")
    return "\n".join(lines)


def map_join_club_error(error: WebApiError) -> str:
    if error.code == "unauthenticated" or error.status_code == 401:
        return JOIN_CLUB_SERVICE_AUTH_ERROR_TEXT
    if error.code in {"web_unavailable", "server_error"} or (error.status_code and error.status_code >= 500):
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT
    return JOIN_CLUB_GENERIC_ERROR_TEXT


def handle_join_club(web_client: WebApiClient, vk_user_id: int | str, bot_token: str, selected_city: str | None = None) -> str:
    selected_city_slug = get_web_known_city_slug(selected_city)
    retried_without_city = False
    try:
        payload = web_client.onboard_vk_client(
            vk_user_id,
            bot_token,
            selected_city_slug=selected_city_slug,
            source="vk",
        )
    except WebApiError as exc:
        if selected_city_slug and (exc.code == "not_found" or exc.status_code == 404):
            try:
                payload = web_client.onboard_vk_client(vk_user_id, bot_token, selected_city_slug=None, source="vk")
                retried_without_city = True
            except WebApiError as retry_exc:
                return map_join_club_error(retry_exc)
        else:
            return map_join_club_error(exc)
    if not isinstance(payload, dict):
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT
    token, user = extract_web_session_from_onboard_response(payload)
    if not token:
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT
    set_web_client_session(vk_user_id, token, user, linked_at=datetime.now(timezone.utc).isoformat())
    return build_join_club_success_text(payload, city_retry_without_slug=retried_without_city)


def main() -> None:
    load_dotenv()
    config = load_config()
    gateway = BackendGateway(config.backend_base_url, config.bot_api_token) if config.vk_bot_use_backend else None
    web_client = WebApiClient(config.web_api_base_url, config.web_api_timeout_seconds)

    vk_session = VkApi(token=config.vk_group_token)
    vk_api = vk_session.get_api()
    logger.info("VK bot started in %s mode", "backend" if config.vk_bot_use_backend else "legacy")

    while True:
        try:
            longpoll = VkBotLongPoll(vk_session, config.vk_group_id)
            for event in longpoll.listen():
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue
                message = event.object.message
                peer_id = message["peer_id"]
                from_id = message.get("from_id")
                raw_text = (message.get("text") or "").strip()
                text = normalize_text(raw_text)
                action, payload = extract_action(message)
                if not from_id:
                    continue

                try:
                    if from_id == config.admin_id and text == "/debug":
                        send_message(vk_api, peer_id, format_debug_status(config, user_state_size=len(USER_STATE)), get_admin_keyboard())
                        continue
                    if from_id == config.admin_id and text == "/health":
                        send_message(vk_api, peer_id, format_health_status(config, gateway), get_admin_keyboard())
                        continue
                    if not gateway:
                        send_message(vk_api, peer_id, "Бот работает в локальном MVP-режиме. Подключение к WEB/CRM сейчас отключено.")
                        continue
                    verify_partner_id = parse_verify_partner_command(raw_text)
                    if verify_partner_id:
                        message_text, keyboard = handle_verify_partner(gateway, from_id, verify_partner_id)
                        send_message(vk_api, peer_id, message_text, keyboard)
                        continue
                    if text in {"/start", "start", "начать"}:
                        profile = vk_api.users.get(user_ids=from_id)[0]
                        gateway.auth_vk_user(from_id, profile.get("first_name"), profile.get("last_name"), profile.get("screen_name"))
                        restore_web_client_session(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, WELCOME_TEXT, get_main_keyboard())
                        continue
                    if action == "main_menu" or text in {normalize_text(BUTTON_MAIN_MENU), "меню"}:
                        clear_user_flow_state(from_id)
                        send_message(vk_api, peer_id, MAIN_MENU_TEXT, get_main_keyboard())
                        continue
                    state = get_user_state(from_id)
                    link_code = parse_link_code_command(raw_text)
                    if link_code:
                        send_message(vk_api, peer_id, handle_vk_link_code(web_client, from_id, link_code, config.bot_api_token), get_main_keyboard())
                        continue
                    if text == "статус привязки":
                        is_linked = restore_web_client_session(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, format_web_link_status(is_linked), get_main_keyboard())
                        continue
                    if action == "join_club" or "присоединиться к клубу" in text:
                        send_message(
                            vk_api,
                            peer_id,
                            handle_join_club(web_client, from_id, config.bot_api_token, selected_city=state.get("selected_city")),
                            get_main_keyboard(),
                        )
                        continue
                    if action == "city_select" or text == normalize_text(BUTTON_CITY):
                        send_message(vk_api, peer_id, "Выберите город", get_city_keyboard())
                        continue
                    if action == "city_selected" and payload.get("city"):
                        city = str(payload.get("city"))
                        # TODO: when WEB/CRM exposes selected_city endpoint, sync this value via BackendGateway.
                        state["selected_city"] = city
                        send_message(vk_api, peer_id, format_city_selected_message(city), get_city_selected_keyboard())
                        continue
                    if action == "partners" or text == normalize_text(BUTTON_PARTNERS):
                        names = WOMEN_CATEGORIES
                        state["categories"] = names
                        send_message(vk_api, peer_id, PARTNERS_INTRO_TEXT, get_categories_keyboard(names))
                        continue
                    if action == "service_search_start":
                        state["awaiting_service_search_query"] = True
                        send_message(vk_api, peer_id, SERVICE_SEARCH_PROMPT_TEXT)
                        continue
                    if state.get("awaiting_service_search_query") and raw_text:
                        state["awaiting_service_search_query"] = False
                        found = gateway.search_services(raw_text)
                        mapped = [
                            {
                                "partner_id": item.get("partner", {}).get("id"),
                                "service_id": item.get("service", {}).get("id"),
                                "service_title": item.get("service", {}).get("title"),
                            }
                            for item in found[:10]
                        ]
                        send_message(vk_api, peer_id, SERVICE_SEARCH_RESULTS_TEXT if mapped else SERVICE_SEARCH_EMPTY_TEXT, get_service_search_results_keyboard(mapped))
                        continue
                    if action == "category_selected":
                        category = payload.get("category")
                        partners = gateway.get_partners(category=None if category == "all" else category)
                        state["last_partners"] = partners
                        message_text = (
                            PARTNERS_FOUND_TEXT
                            if partners
                            else "Партнёры в этой категории пока не найдены. Попробуйте выбрать другую категорию или открыть главное меню."
                        )
                        send_message(vk_api, peer_id, message_text, get_partners_keyboard(partners, category))
                        continue
                    partner_id = payload.get("partner_id") if action == "partner_selected" else parse_partner_command(raw_text)
                    if partner_id:
                        partner_id = int(partner_id)
                        partner = gateway.get_partner(partner_id)
                        state["last_partner_id"] = partner_id
                        send_message(vk_api, peer_id, format_partner_card(partner), get_partner_actions_keyboard(partner_id, has_contacts=True))
                        continue
                    if action == "partner_services":
                        partner_id = int(payload.get("partner_id"))
                        services = gateway.get_partner_services(partner_id)
                        state["last_partner_id"] = partner_id
                        state["last_services"] = services
                        message_text = (
                            SERVICES_INTRO_TEXT
                            if services
                            else "У этого партнёра пока нет доступных предложений. Попробуйте выбрать другого партнёра или открыть главное меню."
                        )
                        send_message(vk_api, peer_id, message_text, get_services_keyboard(partner_id, services))
                        continue
                    service_id = payload.get("service_id") if action == "service_selected" else parse_service_command(raw_text)
                    if service_id:
                        service_id = int(service_id)
                        partner_id = int(payload.get("partner_id") or state.get("last_partner_id") or 0)
                        services = state.get("last_services") or gateway.get_partner_services(partner_id)
                        service = next((s for s in services if int(s.get("id", -1)) == service_id), {"id": service_id})
                        partner = gateway.get_partner(partner_id) if partner_id else {}
                        send_message(vk_api, peer_id, format_service_card(service, partner.get("name"), get_partner_address(partner)), get_service_actions_keyboard(partner_id, service_id))
                        continue
                    code_service_id = int(payload.get("service_id")) if action == "get_discount_code" and payload.get("service_id") else parse_code_command(raw_text)
                    if code_service_id:
                        partner_id = int(payload.get("partner_id") or state.get("last_partner_id") or 0)
                        code_data = gateway.request_discount_code(from_id, partner_id, code_service_id)
                        send_message(vk_api, peer_id, format_code_item(code_data))
                        continue
                    if action == "my_codes" or text == normalize_text(BUTTON_MY_CODES):
                        is_linked = restore_web_client_session(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, f"{MY_PRIVILEGES_FILTER_TEXT}\n\nWEB-привязка: {'активна' if is_linked else 'не активна'}", get_codes_filter_keyboard())
                        continue
                    if action == "codes_filter":
                        status = payload.get("status")
                        codes = gateway.get_my_codes(from_id, status=None if status == "all" else status)
                        send_message(vk_api, peer_id, "\n\n".join(format_code_item(c) for c in codes) if codes else MY_PRIVILEGES_EMPTY_TEXT, get_codes_filter_keyboard())
                        continue
                    if action == "subscription" or text == normalize_text(BUTTON_SUBSCRIPTION):
                        subscription = gateway.get_subscription(from_id)
                        if subscription.get("has_active_subscription"):
                            message_text = SUBSCRIPTION_ACTIVE_TEXT.format(ends_at=format_user_date(subscription.get("ends_at")))
                        else:
                            message_text = SUBSCRIPTION_INACTIVE_TEXT
                        send_message(vk_api, peer_id, message_text, get_main_keyboard())
                        continue
                    if action == "pay" or text in {"оплатить подписку", normalize_text(BUTTON_PAY)}:
                        payment = gateway.create_payment_request(from_id)
                        state["last_payment_request_id"] = payment.get("id")
                        send_message(vk_api, peer_id, format_payment_request_message(payment), get_payment_request_keyboard())
                        continue
                    if action == "payment_paid" or text == "я оплатил":
                        send_message(vk_api, peer_id, handle_payment_paid(gateway, from_id))
                        continue
                    file_url = extract_attachment_url(message)
                    if file_url:
                        gateway.attach_payment_receipt(from_id, file_url)
                        send_message(vk_api, peer_id, PAYMENT_RECEIPT_RECEIVED_TEXT)
                        continue
                    if action == "help" or text in {normalize_text(BUTTON_HELP), "помощь"}:
                        send_message(vk_api, peer_id, HELP_TEXT, get_main_keyboard())
                        continue
                    send_message(vk_api, peer_id, FALLBACK_TEXT, get_main_keyboard())
                except BackendApiError as exc:
                    logger.warning("Backend API error code=%s status=%s", exc.code, exc.status_code)
                    send_message(vk_api, peer_id, format_backend_error_message(exc), get_main_keyboard())
                except Exception:
                    logger.exception("Ошибка обработки")
                    send_message(vk_api, peer_id, "Произошла ошибка. Пожалуйста, попробуйте позже или откройте главное меню.")
                time.sleep(0.01)
        except (ApiError, TimeoutError):
            logger.exception("Критическая ошибка Long Poll, перезапуск через 3 секунды")
            time.sleep(3)
        except Exception:
            logger.exception("Критическая ошибка цикла, перезапуск через 3 секунды")
            time.sleep(3)


if __name__ == "__main__":
    main()
