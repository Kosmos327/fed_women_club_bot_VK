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
from partner_categories import WEB_PARTNER_CATEGORIES, get_web_partner_category_label, get_web_partner_category_slug
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
    get_password_setup_keyboard,
    get_partners_keyboard,
    get_payment_request_keyboard,
    get_web_offers_keyboard,
    get_web_partner_actions_keyboard,
    is_valid_open_link_url,
    get_service_actions_keyboard,
    get_service_search_results_keyboard,
    get_services_keyboard,
    get_verify_error_keyboard,
    get_verify_success_keyboard,
)
from routing import is_link_code_command, parse_code_command, parse_link_code_command, parse_partner_command, parse_service_command, parse_verify_partner_command
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
    MY_PRIVILEGES_WEB_LINK_REQUIRED_TEXT,
    MY_PRIVILEGES_WEB_UNAVAILABLE_TEXT,
    PARTNERS_EMPTY_TEXT,
    PARTNERS_UNKNOWN_CATEGORY_TEXT,
    PARTNERS_WEB_LINK_REQUIRED_TEXT,
    PARTNERS_WEB_UNAVAILABLE_TEXT,
    NO_SUBSCRIPTION_TEXT,
    PARTNERS_FOUND_TEXT,
    PARTNERS_INTRO_TEXT,
    PAYMENT_RECEIPT_RECEIVED_TEXT,
    PAYMENT_RECEIPT_REQUEST_TEXT,
    PAYMENT_REQUEST_NOT_FOUND_TEXT,
    PAYMENT_WEB_LINK_REQUIRED_TEXT,
    PAYMENT_WEB_NOT_FOUND_TEXT,
    PAYMENT_WEB_UNAVAILABLE_TEXT,
    PRIVILEGE_LIMIT_REACHED_TEXT,
    SERVICE_SEARCH_EMPTY_TEXT,
    SERVICE_SEARCH_PROMPT_TEXT,
    SERVICE_SEARCH_RESULTS_TEXT,
    SERVICES_INTRO_TEXT,
    SUBSCRIPTION_ACTIVE_TEXT,
    SUBSCRIPTION_INACTIVE_TEXT,
    SUBSCRIPTION_WEB_LINK_REQUIRED_TEXT,
    SUBSCRIPTION_WEB_UNAVAILABLE_TEXT,
    VERIFY_PARTNER_NOT_FOUND_TEXT,
    VERIFY_PRIVILEGE_FAILED_TEXT,
    VK_LINK_CODE_INVALID_TEXT,
    VK_LINK_CODE_NOT_FOUND_TEXT,
    VK_LINK_CODE_USED_TEXT,
    VK_LINK_CONFLICT_TEXT,
    VK_LINK_INSTRUCTION_TEXT,
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


WEB_VERIFICATION_STATUS_LABELS = {
    "active": "Активна",
    "confirmed": "Использована / Подтверждена",
    "expired": "Истекла",
    "cancelled": "Отменена",
}


def format_privilege_status(status: object) -> str:
    if status is None:
        return "—"
    raw_status = str(status).strip()
    if not raw_status:
        return "—"
    return WEB_VERIFICATION_STATUS_LABELS.get(raw_status.lower(), raw_status)


def _nested_dict_value(data: dict, parent_key: str, child_key: str) -> object | None:
    parent = data.get(parent_key)
    if isinstance(parent, dict):
        return parent.get(child_key)
    return None


def map_web_verification_to_code_item(verification: dict) -> dict:
    partner_name = verification.get("partner_name") or _nested_dict_value(verification, "partner", "name")
    offer_title = verification.get("offer_title") or _nested_dict_value(verification, "offer", "title")
    service_title = offer_title or verification.get("service_title") or verification.get("service_name")
    return {
        "code": verification.get("code"),
        "partner_name": partner_name,
        "service_title": service_title,
        "status": verification.get("status"),
        "created_at": verification.get("created_at"),
        "expires_at": verification.get("expires_at"),
        "confirmed_at": verification.get("confirmed_at"),
    }


def extract_web_verifications(payload: object) -> list[dict]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = None
        for key in ("items", "verifications", "results"):
            if isinstance(payload.get(key), list):
                raw_items = payload.get(key)
                break
        if raw_items is None:
            raw_items = []
    else:
        raw_items = []
    return [item for item in raw_items if isinstance(item, dict)]


def format_code_item(code_data: dict) -> str:
    lines = [
        f"🎁 Код привилегии: {code_data.get('code') or '—'}",
        f"Партнёр: {code_data.get('partner_name') or '—'}",
        f"Статус: {format_privilege_status(code_data.get('status'))}",
        f"Выдана: {format_user_date(code_data.get('created_at'))}",
        f"Действует до: {format_user_date(code_data.get('expires_at'))}",
    ]
    service_name = code_data.get("offer_title") or code_data.get("service_title") or code_data.get("service_name")
    if _is_filled(service_name):
        lines.insert(2, f"Предложение: {service_name}")
    if _is_filled(code_data.get("confirmed_at")):
        lines.append(f"Подтверждена: {format_user_date(code_data.get('confirmed_at'))}")
    return "\n".join(lines)


def format_web_verifications_message(payload: object) -> str:
    verifications = extract_web_verifications(payload)
    if not verifications:
        return MY_PRIVILEGES_EMPTY_TEXT
    return "\n\n".join(format_code_item(map_web_verification_to_code_item(item)) for item in verifications)


def map_web_verifications_error_to_text(error: WebApiError) -> str:
    if error.code in {"unauthenticated", "forbidden"} or error.status_code in {401, 403}:
        return MY_PRIVILEGES_WEB_LINK_REQUIRED_TEXT
    return MY_PRIVILEGES_WEB_UNAVAILABLE_TEXT


def handle_my_codes_filter(
    web_client: WebApiClient,
    vk_user_id: int | str,
    bot_token: str,
    status: str | None = None,
    gateway: BackendGateway | None = None,
) -> str:
    normalized_status = "active" if status == "active" else None
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    logger.info(
        "My privileges requested source=web_api vk_user_id=%s status=%s token_present=%s",
        vk_user_id,
        normalized_status or "all",
        bool(token),
    )
    if not is_linked or not token:
        logger.info(
            "My privileges unavailable source=web_api vk_user_id=%s status=%s token_present=%s reason=no_web_token",
            vk_user_id,
            normalized_status or "all",
            bool(token),
        )
        return MY_PRIVILEGES_WEB_LINK_REQUIRED_TEXT
    try:
        payload = web_client.get_client_verifications(token, normalized_status)
    except WebApiError as exc:
        logger.warning(
            "My privileges WEB API error source=web_api vk_user_id=%s status=%s token_present=%s code=%s http_status=%s",
            vk_user_id,
            normalized_status or "all",
            True,
            exc.code,
            exc.status_code,
        )
        return map_web_verifications_error_to_text(exc)
    logger.info(
        "My privileges loaded source=web_api vk_user_id=%s status=%s token_present=%s count=%s",
        vk_user_id,
        normalized_status or "all",
        True,
        len(extract_web_verifications(payload)),
    )
    return format_web_verifications_message(payload)


def extract_web_catalog_partners(payload: object) -> list[dict]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = None
        for key in ("items", "results", "partners"):
            if isinstance(payload.get(key), list):
                raw_items = payload.get(key)
                break
        if raw_items is None:
            raw_items = []
    else:
        raw_items = []
    return [item for item in raw_items if isinstance(item, dict)]


def get_selected_city_slug_from_profile(profile: dict | None, state: dict | None = None) -> str | None:
    profile = profile or {}
    state = state or {}
    for key in ("selected_city_slug", "city_slug"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    selected_city = profile.get("selected_city")
    if isinstance(selected_city, dict):
        value = selected_city.get("slug")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return get_web_known_city_slug(state.get("selected_city"))


def _truncate_text(value: object, limit: int = 180) -> str | None:
    if not _is_filled(value):
        return None
    text = " ".join(str(value).strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _extract_first_offer(partner: dict) -> dict | None:
    offers = partner.get("offers")
    if isinstance(offers, list):
        return next((offer for offer in offers if isinstance(offer, dict)), None)
    if isinstance(offers, dict):
        return offers
    return None


def _format_partner_benefit(partner: dict) -> str | None:
    offer = _extract_first_offer(partner) or partner
    for key in ("benefit_text", "discount_text", "title", "name"):
        if _is_filled(offer.get(key)):
            return str(offer.get(key)).strip()
    if _is_filled(offer.get("discount_percent")):
        return f"Скидка {format_discount_percent(offer.get('discount_percent'))}"
    return None


def format_web_partner_compact(partner: dict) -> str:
    lines = [str(partner.get("name") or "Партнёр").strip()]
    category = partner.get("category_title") or partner.get("category") or get_web_partner_category_label(partner.get("category_slug"))
    if _is_filled(category):
        lines.append(f"Категория: {category}")
    address = partner.get("address") or partner.get("city_name")
    if _is_filled(address):
        lines.append(f"Адрес/город: {address}")
    description = _truncate_text(partner.get("description"))
    if description:
        lines.extend(["", description])
    if partner.get("is_verified") is True:
        lines.append("✅ Проверенный партнёр")
    benefit = _format_partner_benefit(partner)
    if benefit:
        lines.append(f"Выгода: {benefit}")
    return "\n".join(lines)


def format_web_partners_list(partners: list[dict]) -> str:
    if not partners:
        return PARTNERS_EMPTY_TEXT
    return "\n\n".join(format_web_partner_compact(partner) for partner in partners[:10])


def _cache_web_catalog_partners(state: dict, partners: list[dict], city_slug: str | None, category_slug: str | None) -> None:
    partners_by_id = {}
    for partner in partners:
        partner_id = partner.get("id")
        if partner_id is not None:
            partners_by_id[str(partner_id)] = partner
    state["web_catalog_partners_by_id"] = partners_by_id
    state["web_catalog_city_slug"] = city_slug
    state["web_catalog_category_slug"] = category_slug


def extract_web_partner_offers(payload: object) -> list[dict]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = None
        for key in ("items", "offers", "results"):
            if isinstance(payload.get(key), list):
                raw_items = payload.get(key)
                break
        if raw_items is None:
            raw_items = []
    else:
        raw_items = []
    return [item for item in raw_items if isinstance(item, dict)]


def _cache_web_partner_offers(state: dict, partner_id: int, offers: list[dict]) -> None:
    offers_by_partner_id = state.setdefault("web_partner_offers_by_partner_id", {})
    offers_by_id = state.setdefault("web_partner_offers_by_id", {})
    offers_by_partner_id[str(partner_id)] = offers
    for offer in offers:
        offer_id = offer.get("id")
        if offer_id is not None:
            offers_by_id[str(offer_id)] = {**offer, "partner_id": partner_id}


def extract_web_verification(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in ("verification", "session", "item"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def format_web_created_verification_message(payload: object, partner: dict | None = None, offer: dict | None = None) -> str:
    verification = extract_web_verification(payload)
    code_item = map_web_verification_to_code_item(verification)
    partner = partner or {}
    offer = offer or {}
    if not _is_filled(code_item.get("partner_name")) and _is_filled(partner.get("name")):
        code_item["partner_name"] = partner.get("name")
    if not _is_filled(code_item.get("service_title")) and _is_filled(offer.get("title") or offer.get("name")):
        code_item["service_title"] = offer.get("title") or offer.get("name")
    return (
        f"{format_code_item(code_item)}\n\n"
        "Покажите этот код партнёру перед оплатой/получением услуги."
    )


def _is_no_subscription_error(error: WebApiError) -> bool:
    detail = (error.detail or "").strip().lower()
    return error.code == "no_subscription" or detail == "no_subscription" or error.status_code == 403


def map_web_partner_privilege_error_to_text(error: WebApiError) -> str:
    if _is_no_subscription_error(error):
        return "Для получения привилегии нужна активная подписка."
    if error.code == "not_found" or error.status_code == 404:
        return "Партнёр или предложение недоступны."
    if error.code in {"unauthenticated", "forbidden"} or error.status_code in {401, 403}:
        return PARTNERS_WEB_LINK_REQUIRED_TEXT
    return "Не удалось получить привилегию. Попробуйте позже или откройте главное меню."


def handle_web_partner_selected(
    web_client: WebApiClient,
    vk_user_id: int | str,
    bot_token: str,
    partner_id: int,
) -> tuple[str, str]:
    state = get_user_state(int(vk_user_id))
    partner = (state.get("web_catalog_partners_by_id") or {}).get(str(partner_id))
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    if not is_linked or not token:
        return PARTNERS_WEB_LINK_REQUIRED_TEXT, get_main_keyboard()
    try:
        payload = web_client.get_client_partner_offers(token, partner_id)
    except WebApiError as exc:
        logger.warning(
            "Partner offers WEB API error source=web_api vk_user_id=%s partner_id=%s token_present=%s code=%s http_status=%s",
            vk_user_id,
            partner_id,
            True,
            exc.code,
            exc.status_code,
        )
        text = map_web_partner_privilege_error_to_text(exc)
        keyboard = get_no_subscription_keyboard() if _is_no_subscription_error(exc) else get_nav_keyboard()
        return text, keyboard
    offers = extract_web_partner_offers(payload)
    _cache_web_partner_offers(state, partner_id, offers)
    state["last_partner_id"] = partner_id
    detail = format_web_partner_compact(partner) if isinstance(partner, dict) else f"Партнёр {partner_id}"
    if offers:
        return f"{detail}\n\nВыберите предложение:", get_web_offers_keyboard(partner_id, offers)
    return f"{detail}\n\nУ партнёра пока нет активных предложений.", get_web_partner_actions_keyboard(partner_id)


def handle_web_offer_selected(
    web_client: WebApiClient,
    vk_user_id: int | str,
    bot_token: str,
    partner_id: int,
    offer_id: int | None = None,
) -> tuple[str, str]:
    state = get_user_state(int(vk_user_id))
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    if not is_linked or not token:
        return PARTNERS_WEB_LINK_REQUIRED_TEXT, get_main_keyboard()
    try:
        payload = web_client.create_client_partner_verification(token, partner_id, offer_id)
    except WebApiError as exc:
        logger.warning(
            "Partner verification WEB API error source=web_api vk_user_id=%s partner_id=%s offer_id=%s token_present=%s code=%s http_status=%s",
            vk_user_id,
            partner_id,
            offer_id,
            True,
            exc.code,
            exc.status_code,
        )
        text = map_web_partner_privilege_error_to_text(exc)
        keyboard = get_no_subscription_keyboard() if _is_no_subscription_error(exc) else get_nav_keyboard()
        return text, keyboard
    partner = (state.get("web_catalog_partners_by_id") or {}).get(str(partner_id))
    offer = (state.get("web_partner_offers_by_id") or {}).get(str(offer_id)) if offer_id is not None else None
    return format_web_created_verification_message(payload, partner=partner, offer=offer), get_verify_success_keyboard()


def handle_partners_start(web_client: WebApiClient, vk_user_id: int | str, bot_token: str) -> tuple[str, str]:
    state = get_user_state(int(vk_user_id))
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    logger.info(
        "Partners start requested source=web_api vk_user_id=%s city_slug=%s category_slug=%s token_present=%s",
        vk_user_id,
        state.get("web_catalog_city_slug"),
        None,
        bool(token),
    )
    if not is_linked or not token:
        return PARTNERS_WEB_LINK_REQUIRED_TEXT, get_main_keyboard()
    try:
        profile = web_client.get_client_profile(token)
    except WebApiError as exc:
        logger.warning(
            "Partners profile WEB API error source=web_api vk_user_id=%s city_slug=%s category_slug=%s token_present=%s code=%s http_status=%s",
            vk_user_id,
            None,
            None,
            True,
            exc.code,
            exc.status_code,
        )
        return PARTNERS_WEB_UNAVAILABLE_TEXT, get_main_keyboard()
    city_slug = get_selected_city_slug_from_profile(profile, state)
    state["web_client_profile"] = profile
    state["web_catalog_city_slug"] = city_slug
    state["categories"] = list(WEB_PARTNER_CATEGORIES)
    return PARTNERS_INTRO_TEXT, get_categories_keyboard(list(WEB_PARTNER_CATEGORIES))


def handle_category_selected(
    web_client: WebApiClient,
    vk_user_id: int | str,
    bot_token: str,
    category: str | None,
    category_slug: str | None = None,
    gateway: BackendGateway | None = None,
) -> tuple[str, str]:
    state = get_user_state(int(vk_user_id))
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    if is_linked and token:
        requested_slug = category_slug if category_slug else None
        if category == "all":
            requested_slug = None
        elif not requested_slug:
            requested_slug = get_web_partner_category_slug(category)
            if requested_slug is None:
                logger.info(
                    "Partners category unknown source=web_api vk_user_id=%s city_slug=%s category_slug=%s token_present=%s",
                    vk_user_id,
                    state.get("web_catalog_city_slug"),
                    category,
                    True,
                )
                return PARTNERS_UNKNOWN_CATEGORY_TEXT, get_categories_keyboard(list(WEB_PARTNER_CATEGORIES))
        city_slug = state.get("web_catalog_city_slug")
        if not city_slug:
            profile = state.get("web_client_profile") if isinstance(state.get("web_client_profile"), dict) else {}
            city_slug = get_selected_city_slug_from_profile(profile, state)
            state["web_catalog_city_slug"] = city_slug
        logger.info(
            "Partners category requested source=web_api vk_user_id=%s city_slug=%s category_slug=%s token_present=%s",
            vk_user_id,
            city_slug,
            requested_slug,
            True,
        )
        try:
            payload = web_client.get_client_catalog_partners(token, city_slug=city_slug, category_slug=requested_slug)
        except WebApiError as exc:
            logger.warning(
                "Partners WEB API error source=web_api vk_user_id=%s city_slug=%s category_slug=%s token_present=%s code=%s http_status=%s",
                vk_user_id,
                city_slug,
                requested_slug,
                True,
                exc.code,
                exc.status_code,
            )
            return PARTNERS_WEB_UNAVAILABLE_TEXT, get_categories_keyboard(list(WEB_PARTNER_CATEGORIES))
        partners = extract_web_catalog_partners(payload)
        _cache_web_catalog_partners(state, partners, city_slug, requested_slug)
        state["last_partners"] = partners
        return format_web_partners_list(partners), get_partners_keyboard(partners, category)

    if gateway is None:
        return PARTNERS_WEB_LINK_REQUIRED_TEXT, get_main_keyboard()
    partners = gateway.get_partners(category=None if category == "all" else category)
    state["last_partners"] = partners
    message_text = PARTNERS_FOUND_TEXT if partners else PARTNERS_EMPTY_TEXT
    return message_text, get_partners_keyboard(partners, category)


def format_city_selected_message(city: str) -> str:
    return f"Город выбран: {city}. Теперь покажем партнёров и предложения рядом."


WEB_PAYMENT_STATUS_LABELS = {
    "pending": "Ожидает оплаты",
    "paid": "Оплачено, ожидает проверки",
    "approved": "Подтверждено",
    "rejected": "Отклонено",
}


def format_payment_request_message(payment: dict) -> str:
    amount = payment.get("amount") or "—"
    instructions = (payment.get("payment_instructions") or "").strip()
    parts = [f"Сумма: {amount}"]
    if instructions:
        parts.append(instructions)
    parts.append("После оплаты нажмите «✅ Я оплатил» и отправьте скрин оплаты.")
    return "\n".join(parts)


def format_web_payment_status(status: object) -> str:
    raw_status = str(status or "pending").strip().lower()
    return WEB_PAYMENT_STATUS_LABELS.get(raw_status, raw_status or "—")


def format_web_payment_request(payment: dict) -> str:
    lines = [
        f"ID заявки: {payment.get('id') or '—'}",
        f"Сумма: {payment.get('amount') or '—'}",
        f"Статус: {format_web_payment_status(payment.get('status'))}",
        f"Создана: {format_user_date(payment.get('created_at'))}",
    ]
    comment = payment.get("comment")
    if comment:
        lines.append(f"Комментарий: {comment}")
    access_until = payment.get("access_until")
    if access_until:
        lines.append(f"Доступ до: {format_user_date(access_until)}")
    return "\n".join(lines)


def format_web_payment_created_message(payment: dict) -> str:
    instructions = (
        (payment.get("payment_instructions") or payment.get("instructions") or "").strip()
        or "Оплатите подписку по реквизитам из WEB-кабинета или по инструкции администратора клуба."
    )
    return "\n\n".join(
        [
            "Заявка на оплату создана",
            format_web_payment_request({**payment, "status": payment.get("status") or "pending"}),
            instructions,
            "После оплаты нажмите «✅ Я оплатил». Подписка не продлевается автоматически: администратор проверит оплату вручную.",
        ]
    )


def format_web_payment_paid_message(payment: dict) -> str:
    return "\n\n".join(
        [
            "Спасибо! Мы отметили заявку как оплаченную.",
            format_web_payment_request({**payment, "status": payment.get("status") or "paid"}),
            "Администратор проверит оплату вручную. Подписка будет обновлена только после подтверждения.",
        ]
    )


def map_web_payment_error_to_text(exc: WebApiError) -> str:
    if exc.status_code in {401, 403} or exc.code in {"unauthenticated", "forbidden"}:
        return PAYMENT_WEB_LINK_REQUIRED_TEXT
    if exc.status_code == 404 or exc.code == "not_found":
        return PAYMENT_WEB_NOT_FOUND_TEXT
    return PAYMENT_WEB_UNAVAILABLE_TEXT


def extract_web_payment_requests(payload: list[dict] | dict) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "payment_requests", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def choose_latest_pending_or_paid_payment_request(payload: list[dict] | dict) -> dict | None:
    for payment in extract_web_payment_requests(payload):
        if str(payment.get("status") or "").strip().lower() in {"pending", "paid"}:
            return payment
    return None


def handle_web_payment_request(web_client: WebApiClient, vk_user_id: int, bot_token: str) -> tuple[str, str]:
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id) if is_linked else None
    if not token:
        logger.info(
            "Payment request skipped source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s",
            vk_user_id,
            None,
            False,
            "missing_token",
        )
        return PAYMENT_WEB_LINK_REQUIRED_TEXT, get_main_keyboard()
    try:
        payment = web_client.create_client_payment_request(token, amount=None, source="vk", comment=None)
    except WebApiError as exc:
        logger.warning(
            "Payment request failed source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s code=%s",
            vk_user_id,
            None,
            True,
            exc.status_code,
            exc.code,
        )
        return map_web_payment_error_to_text(exc), get_main_keyboard()
    payment_request_id = payment.get("id")
    get_user_state(vk_user_id)["last_payment_request_id"] = payment_request_id
    logger.info(
        "Payment request created source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s",
        vk_user_id,
        payment_request_id,
        True,
        payment.get("status") or "pending",
    )
    return format_web_payment_created_message(payment), get_payment_request_keyboard()


def handle_web_payment_paid(web_client: WebApiClient, vk_user_id: int, bot_token: str) -> str:
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id) if is_linked else None
    if not token:
        logger.info(
            "Payment mark-paid skipped source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s",
            vk_user_id,
            None,
            False,
            "missing_token",
        )
        return PAYMENT_WEB_LINK_REQUIRED_TEXT

    state = get_user_state(vk_user_id)
    payment_request_id = state.get("last_payment_request_id")
    if not payment_request_id:
        try:
            latest = choose_latest_pending_or_paid_payment_request(web_client.get_client_payment_requests(token))
        except WebApiError as exc:
            logger.warning(
                "Payment requests lookup failed source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s code=%s",
                vk_user_id,
                None,
                True,
                exc.status_code,
                exc.code,
            )
            return map_web_payment_error_to_text(exc)
        if latest:
            payment_request_id = latest.get("id")
            state["last_payment_request_id"] = payment_request_id
    if not payment_request_id:
        logger.info(
            "Payment mark-paid skipped source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s",
            vk_user_id,
            None,
            True,
            "missing_payment_request",
        )
        return PAYMENT_REQUEST_NOT_FOUND_TEXT

    try:
        payment = web_client.mark_client_payment_paid(
            token,
            int(payment_request_id),
            comment="Клиент нажал Я оплатил в VK",
        )
    except WebApiError as exc:
        logger.warning(
            "Payment mark-paid failed source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s code=%s",
            vk_user_id,
            payment_request_id,
            True,
            exc.status_code,
            exc.code,
        )
        return map_web_payment_error_to_text(exc)
    logger.info(
        "Payment marked paid source=web_api vk_user_id=%s payment_request_id=%s token_present=%s status=%s",
        vk_user_id,
        payment_request_id,
        True,
        payment.get("status") or "paid",
    )
    return format_web_payment_paid_message(payment)


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "active"}:
            return True
        if normalized in {"false", "0", "no", "n", "inactive", "expired"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def is_web_subscription_active(subscription: dict) -> bool:
    for key in ("has_active_subscription", "is_active"):
        active = _coerce_bool(subscription.get(key))
        if active is not None:
            return active
    status = str(subscription.get("status") or "").strip().lower()
    return status == "active"


def get_web_subscription_ends_at(subscription: dict) -> str | None:
    for key in ("ends_at", "expires_at", "paid_until"):
        value = subscription.get(key)
        if value:
            return str(value)
    return None


def format_web_subscription_message(subscription: dict) -> str:
    if is_web_subscription_active(subscription):
        return SUBSCRIPTION_ACTIVE_TEXT.format(ends_at=format_user_date(get_web_subscription_ends_at(subscription)))
    return SUBSCRIPTION_INACTIVE_TEXT


def map_web_subscription_error_to_text(error: WebApiError) -> str:
    if error.code in {"unauthenticated", "forbidden"} or error.status_code in {401, 403}:
        return SUBSCRIPTION_WEB_LINK_REQUIRED_TEXT
    return SUBSCRIPTION_WEB_UNAVAILABLE_TEXT


def handle_subscription_status(
    web_client: WebApiClient,
    vk_user_id: int | str,
    bot_token: str,
    gateway: BackendGateway | None = None,
) -> str:
    is_linked = restore_web_client_session(web_client, vk_user_id, bot_token)
    token = get_web_client_token(vk_user_id)
    logger.info(
        "Subscription status requested source=web_api vk_user_id=%s web_token_present=%s",
        vk_user_id,
        bool(token),
    )
    if not is_linked or not token:
        logger.info(
            "Subscription status unavailable source=web_api vk_user_id=%s web_token_present=%s reason=no_web_token",
            vk_user_id,
            bool(token),
        )
        return SUBSCRIPTION_WEB_LINK_REQUIRED_TEXT
    try:
        subscription = web_client.get_client_subscription(token)
    except WebApiError as exc:
        logger.warning(
            "Subscription WEB API error source=web_api vk_user_id=%s web_token_present=%s code=%s status=%s",
            vk_user_id,
            True,
            exc.code,
            exc.status_code,
        )
        return map_web_subscription_error_to_text(exc)
    if not isinstance(subscription, dict):
        logger.warning(
            "Subscription WEB API returned unexpected payload source=web_api vk_user_id=%s web_token_present=%s",
            vk_user_id,
            True,
        )
        return SUBSCRIPTION_WEB_UNAVAILABLE_TEXT
    logger.info(
        "Subscription status loaded source=web_api vk_user_id=%s web_token_present=%s active=%s",
        vk_user_id,
        True,
        is_web_subscription_active(subscription),
    )
    return format_web_subscription_message(subscription)


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


def format_link_success(user: dict | None = None) -> str:
    return (
        "VK привязан к WEB-кабинету. Теперь доступны подписка, партнёры и мои привилегии.\n\n"
        "Откройте главное меню или нажмите нужную кнопку ниже."
    )


def _normalize_error_detail(detail: str | None) -> str:
    return (detail or "").strip().lower()


def map_web_api_error_to_link_text(error: WebApiError) -> str:
    detail = _normalize_error_detail(error.detail)
    if "link code already used" in detail or "already used" in detail:
        return VK_LINK_CODE_USED_TEXT
    if any(marker in detail for marker in ("expired", "invalid", "not found", "not_found")) or error.code == "not_found" or error.status_code == 404:
        return VK_LINK_CODE_NOT_FOUND_TEXT
    if any(marker in detail for marker in ("conflict", "already linked", "another profile", "vk already linked")) or error.code == "conflict" or error.status_code == 409:
        return VK_LINK_CONFLICT_TEXT
    if error.code in {"unauthenticated", "forbidden"} or error.status_code in {401, 403}:
        return VK_LINK_SERVICE_AUTH_ERROR_TEXT
    if error.code in {"client_error", "validation_error"} or error.status_code in {400, 422}:
        return VK_LINK_CODE_INVALID_TEXT
    return VK_LINK_WEB_UNAVAILABLE_TEXT


def handle_vk_link_code(web_client: WebApiClient, vk_user_id: int | str, code: str, bot_token: str) -> str:
    normalized_code = str(code or "").strip().upper()
    if not normalized_code:
        logger.info(
            "vk_link_code_exchange",
            extra={
                "vk_user_id": vk_user_id,
                "action": "vk_link_code_exchange",
                "result": "error",
                "error_code": "missing_code",
                "status": None,
                "token_present": False,
            },
        )
        return VK_LINK_INSTRUCTION_TEXT
    try:
        payload = web_client.exchange_vk_link_code(vk_user_id, normalized_code, bot_token)
    except WebApiError as exc:
        logger.info(
            "vk_link_code_exchange",
            extra={
                "vk_user_id": vk_user_id,
                "action": "vk_link_code_exchange",
                "result": "error",
                "error_code": exc.code,
                "status": exc.status_code,
                "token_present": False,
            },
        )
        return map_web_api_error_to_link_text(exc)
    if not isinstance(payload, dict):
        logger.info(
            "vk_link_code_exchange",
            extra={
                "vk_user_id": vk_user_id,
                "action": "vk_link_code_exchange",
                "result": "error",
                "error_code": "invalid_payload",
                "status": None,
                "token_present": False,
            },
        )
        return VK_LINK_WEB_UNAVAILABLE_TEXT
    token = _extract_web_token(payload)
    token_present = bool(token)
    if not token:
        logger.info(
            "vk_link_code_exchange",
            extra={
                "vk_user_id": vk_user_id,
                "action": "vk_link_code_exchange",
                "result": "error",
                "error_code": "missing_token",
                "status": None,
                "token_present": token_present,
            },
        )
        return VK_LINK_WEB_UNAVAILABLE_TEXT
    user = _extract_web_user(payload)
    set_web_client_session(vk_user_id, token, user, linked_at=datetime.now(timezone.utc).isoformat())
    logger.info(
        "vk_link_code_exchange",
        extra={
            "vk_user_id": vk_user_id,
            "action": "vk_link_code_exchange",
            "result": "success",
            "error_code": None,
            "status": None,
            "token_present": token_present,
        },
    )
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

    password_setup_url = response.get("password_setup_url")
    password_setup_required = response.get("password_setup_required") is True
    login = response.get("login")

    lines = [
        first_line,
        "",
        "Вы уже можете открыть bloomclub.ru и посмотреть каталог партнёров.",
        "Подписка пока не активна до оплаты, поэтому подтверждение привилегий будет доступно после оплаты.",
        "WEB-кабинет: доступ для бота активен.",
        "Явная VK-привязка: через код из WEB-кабинета. "
        "Создайте код в WEB-кабинете и отправьте сюда: Привязать КОД",
    ]

    if password_setup_required and is_valid_open_link_url(password_setup_url):
        lines.extend(
            [
                "",
                "Чтобы входить в WEB-кабинет самостоятельно, нажмите кнопку ниже, чтобы задать пароль.",
                "Ссылка действует 60 минут.",
                "Пароль не отправляйте в VK.",
            ]
        )
        if isinstance(login, str) and login.strip():
            lines.append(f"Логин: {login.strip()}")
    elif response.get("password_setup_required") is False:
        lines.extend(["", "Пароль для WEB-кабинета уже установлен. Войти можно на сайте."])
    else:
        lines.extend(["", "Пароль в VK не отправляется. Вход по паролю в WEB будет подключён через безопасную установку пароля."])

    if city_retry_without_slug:
        lines.append("Город можно будет выбрать позже в личном кабинете.")
    return "\n".join(lines)


def map_join_club_error(error: WebApiError) -> str:
    if error.code == "unauthenticated" or error.status_code == 401:
        return JOIN_CLUB_SERVICE_AUTH_ERROR_TEXT
    if error.code in {"web_unavailable", "server_error"} or (error.status_code and error.status_code >= 500):
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT
    return JOIN_CLUB_GENERIC_ERROR_TEXT


def should_show_password_setup_button(response: dict) -> bool:
    return response.get("password_setup_required") is True and is_valid_open_link_url(response.get("password_setup_url"))


def handle_join_club_result(web_client: WebApiClient, vk_user_id: int | str, bot_token: str, selected_city: str | None = None) -> tuple[str, str]:
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
                return map_join_club_error(retry_exc), get_main_keyboard()
        else:
            return map_join_club_error(exc), get_main_keyboard()
    if not isinstance(payload, dict):
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT, get_main_keyboard()
    token, user = extract_web_session_from_onboard_response(payload)
    if not token:
        return JOIN_CLUB_WEB_UNAVAILABLE_TEXT, get_main_keyboard()
    set_web_client_session(vk_user_id, token, user, linked_at=datetime.now(timezone.utc).isoformat())
    keyboard = (
        get_password_setup_keyboard(payload.get("password_setup_url"))
        if should_show_password_setup_button(payload)
        else get_main_keyboard()
    )
    return build_join_club_success_text(payload, city_retry_without_slug=retried_without_city), keyboard


def handle_join_club(web_client: WebApiClient, vk_user_id: int | str, bot_token: str, selected_city: str | None = None) -> str:
    message, _keyboard = handle_join_club_result(web_client, vk_user_id, bot_token, selected_city=selected_city)
    return message


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
                    if is_link_code_command(raw_text):
                        send_message(vk_api, peer_id, handle_vk_link_code(web_client, from_id, "", config.bot_api_token), get_main_keyboard())
                        continue
                    if text == "статус привязки":
                        is_linked = restore_web_client_session(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, format_web_link_status(is_linked), get_main_keyboard())
                        continue
                    if action == "join_club" or "присоединиться к клубу" in text:
                        message_text, keyboard = handle_join_club_result(
                            web_client,
                            from_id,
                            config.bot_api_token,
                            selected_city=state.get("selected_city"),
                        )
                        send_message(vk_api, peer_id, message_text, keyboard)
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
                        message_text, keyboard = handle_partners_start(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, message_text, keyboard)
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
                        category_slug = payload.get("category_slug")
                        message_text, keyboard = handle_category_selected(
                            web_client,
                            from_id,
                            config.bot_api_token,
                            category=category,
                            category_slug=category_slug,
                            gateway=gateway,
                        )
                        send_message(vk_api, peer_id, message_text, keyboard)
                        continue
                    if action == "web_offer_selected":
                        partner_id = int(payload.get("partner_id") or state.get("last_partner_id") or 0)
                        offer_id = int(payload.get("offer_id")) if payload.get("offer_id") is not None else None
                        message_text, keyboard = handle_web_offer_selected(web_client, from_id, config.bot_api_token, partner_id, offer_id)
                        send_message(vk_api, peer_id, message_text, keyboard)
                        continue
                    if action == "web_get_privilege":
                        partner_id = int(payload.get("partner_id") or state.get("last_partner_id") or 0)
                        message_text, keyboard = handle_web_offer_selected(web_client, from_id, config.bot_api_token, partner_id, None)
                        send_message(vk_api, peer_id, message_text, keyboard)
                        continue
                    partner_id = payload.get("partner_id") if action == "partner_selected" else parse_partner_command(raw_text)
                    if partner_id:
                        partner_id = int(partner_id)
                        cached_web_partner = (state.get("web_catalog_partners_by_id") or {}).get(str(partner_id))
                        state["last_partner_id"] = partner_id
                        if isinstance(cached_web_partner, dict):
                            message_text, keyboard = handle_web_partner_selected(web_client, from_id, config.bot_api_token, partner_id)
                            send_message(vk_api, peer_id, message_text, keyboard)
                            continue
                        partner = gateway.get_partner(partner_id)
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
                        send_message(vk_api, peer_id, f"{MY_PRIVILEGES_FILTER_TEXT}\n\nWEB-кабинет: {'доступ активен' if is_linked else 'доступ не активен'}", get_codes_filter_keyboard())
                        continue
                    if action == "codes_filter":
                        status = payload.get("status")
                        message_text = handle_my_codes_filter(web_client, from_id, config.bot_api_token, status=status, gateway=gateway)
                        send_message(vk_api, peer_id, message_text, get_codes_filter_keyboard())
                        continue
                    if action == "subscription" or text == normalize_text(BUTTON_SUBSCRIPTION):
                        message_text = handle_subscription_status(web_client, from_id, config.bot_api_token, gateway=gateway)
                        send_message(vk_api, peer_id, message_text, get_main_keyboard())
                        continue
                    if action == "pay" or text in {"оплатить подписку", normalize_text(BUTTON_PAY)}:
                        message_text, keyboard = handle_web_payment_request(web_client, from_id, config.bot_api_token)
                        send_message(vk_api, peer_id, message_text, keyboard)
                        continue
                    if action == "payment_paid" or text == "я оплатил":
                        send_message(vk_api, peer_id, handle_web_payment_paid(web_client, from_id, config.bot_api_token))
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
