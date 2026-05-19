import json
from typing import Iterable
from urllib.parse import urlparse

from partner_categories import WebPartnerCategory

BUTTON_SUBSCRIPTION = "💗 Подписка"
BUTTON_JOIN_CLUB = "💗 Присоединиться к клубу"
BUTTON_PARTNERS = "✨ Партнёры и скидки"
BUTTON_MY_CODES = "🎁 Мои привилегии"
BUTTON_PAY = "💳 Оплатить / Продлить"
BUTTON_CITY = "🌸 Выбрать город"
BUTTON_HELP = "❓ Помощь"
BUTTON_MAIN_MENU = "🏠 Главное меню"
BUTTON_PASSWORD_SETUP = "Установить новый пароль"
BUTTON_WEB_LOGIN = "Открыть WEB-кабинет"
BUTTON_OTHER_CITY = "Другой город"
BUTTON_SKIP = "Пропустить"
BUTTON_MORE_PARTNERS = "Ещё партнёры"
BUTTON_CHANGE_CITY = "Сменить город"
BUTTON_BACK_TO_PARTNERS = "Назад к партнёрам"
BUTTON_BACK_TO_PARTNER = "Назад к партнёру"
BUTTON_GET_CODE = "Получить код"
BUTTON_OPEN_SITE = "Открыть на сайте"

VK_KEYBOARD_MAX_ROWS = 5
VK_KEYBOARD_MAX_BUTTONS_PER_ROW = 5
PARTNERS_PAGE_SIZE = 5

CITIES = [
    "Новосибирск",
    "Москва",
    "Санкт-Петербург",
    "Екатеринбург",
    "Казань",
]

WOMEN_CATEGORIES = [
    "Красота",
    "Маникюр / педикюр",
    "Волосы / окрашивание",
    "Брови / ресницы",
    "Косметология",
    "Массаж / SPA",
    "Фитнес / йога",
    "Здоровье",
    "Психология",
    "Одежда / аксессуары",
    "Кафе / рестораны",
    "Обучение / мастер-классы",
    "Фотосессии",
    "Цветы / подарки",
    "Другое",
]


def _button(label: str, action: str, color: str = "secondary", **payload) -> dict:
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": json.dumps({"action": action, **payload}, ensure_ascii=False),
        },
        "color": color,
    }


def is_valid_open_link_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_button(label: str, url: str) -> dict:
    return {"action": {"type": "open_link", "label": label, "link": url.strip()}}


def _normalize_rows(rows: Iterable[Iterable[dict]]) -> list[list[dict]]:
    safe_rows: list[list[dict]] = []
    for row in rows:
        buttons = [button for button in row if isinstance(button, dict)]
        if buttons:
            safe_rows.append(buttons[:VK_KEYBOARD_MAX_BUTTONS_PER_ROW])
        if len(safe_rows) >= VK_KEYBOARD_MAX_ROWS:
            break
    return safe_rows


def _keyboard(rows: Iterable[Iterable[dict]], one_time: bool = False) -> str:
    return json.dumps(
        {"one_time": one_time, "inline": False, "buttons": _normalize_rows(rows)},
        ensure_ascii=False,
    )


def is_valid_keyboard(keyboard: object) -> bool:
    if keyboard is None:
        return True
    try:
        payload = json.loads(keyboard) if isinstance(keyboard, str) else keyboard
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    buttons = payload.get("buttons")
    if not isinstance(buttons, list) or len(buttons) > VK_KEYBOARD_MAX_ROWS:
        return False
    for row in buttons:
        if not isinstance(row, list) or len(row) > VK_KEYBOARD_MAX_BUTTONS_PER_ROW:
            return False
        for button in row:
            if not isinstance(button, dict) or not isinstance(button.get("action"), dict):
                return False
    return True


def _main_keyboard_rows() -> list[list[dict]]:
    return [
        [_button(BUTTON_JOIN_CLUB, "join_club", "primary")],
        [_button(BUTTON_SUBSCRIPTION, "subscription", "primary")],
        [_button(BUTTON_PARTNERS, "partners", "primary")],
        [_button(BUTTON_MY_CODES, "my_codes"), _button(BUTTON_PAY, "pay", "positive")],
        [_button(BUTTON_CITY, "city_select"), _button(BUTTON_HELP, "help")],
    ]


def get_main_keyboard() -> str:
    return _keyboard(_main_keyboard_rows())


def get_safe_fallback_keyboard() -> str:
    return _keyboard([[_button(BUTTON_PARTNERS, "partners", "primary")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_password_setup_keyboard(password_setup_url: object) -> str:
    return get_web_onboarding_keyboard(password_setup_url=password_setup_url)


def get_web_onboarding_keyboard(password_setup_url: object = None, web_login_url: object = None) -> str:
    rows = []
    if is_valid_open_link_url(web_login_url):
        rows.append([_url_button(BUTTON_WEB_LOGIN, str(web_login_url))])
    if is_valid_open_link_url(password_setup_url):
        rows.append([_url_button(BUTTON_PASSWORD_SETUP, str(password_setup_url))])
    rows.extend(_main_keyboard_rows()[: max(0, VK_KEYBOARD_MAX_ROWS - len(rows))])
    return _keyboard(rows)


def get_nav_keyboard() -> str:
    return _keyboard([[_button(BUTTON_MAIN_MENU, "main_menu", "primary")]])


def get_city_keyboard() -> str:
    return _keyboard(
        [
            [_button("Новосибирск", "city_selected", "primary", city="Новосибирск")],
            [_button(BUTTON_OTHER_CITY, "city_other")],
            [_button("Назад в меню", "main_menu")],
        ]
    )


def get_profile_survey_city_keyboard(cities: list[dict] | None = None) -> str:
    rows: list[list[dict]] = []
    for city in (cities or [])[:3]:
        name = str(city.get("name") or "").strip()
        slug = str(city.get("slug") or "").strip()
        if not name or not slug:
            continue
        rows.append([_button(name, "profile_city_selected", "primary", city_name=name, city_slug=slug)])
    rows.append([_button(BUTTON_OTHER_CITY, "profile_city_other"), _button(BUTTON_SKIP, "profile_survey_skip")])
    rows.append([_button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows[:VK_KEYBOARD_MAX_ROWS])


def get_profile_survey_done_keyboard() -> str:
    return _keyboard(
        [
            [_button(BUTTON_PARTNERS, "partners", "primary")],
            [_button(BUTTON_SUBSCRIPTION, "subscription", "primary")],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_city_selected_keyboard() -> str:
    return _keyboard(
        [
            [_button(BUTTON_PARTNERS, "partners", "primary")],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def _category_label_and_slug(category: str | dict | WebPartnerCategory) -> tuple[str, str | None]:
    if isinstance(category, WebPartnerCategory):
        return category.label, category.slug
    if isinstance(category, dict):
        label = str(category.get("label") or category.get("title") or category.get("name") or "Категория")
        slug = category.get("slug") or category.get("category_slug")
        return label, str(slug) if slug else None
    return str(category), None


def get_categories_keyboard(categories: list[str | dict | WebPartnerCategory] | None = None) -> str:
    category_names = categories or WOMEN_CATEGORIES
    rows = [[_button("Все категории", "category_selected", "primary", category="all", category_slug=None)]]
    for category in category_names[:2]:
        label, slug = _category_label_and_slug(category)
        rows.append([_button(label, "category_selected", category=label, category_slug=slug)])
    rows.append([_button(BUTTON_CHANGE_CITY, "city_select")])
    rows.append([_button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_partner_catalog_keyboard(partners_count: int, has_more: bool = False) -> str:
    number_buttons = [_button(str(index), "partner_number_selected", "primary", number=index) for index in range(1, min(partners_count, PARTNERS_PAGE_SIZE) + 1)]
    rows: list[list[dict]] = []
    if number_buttons:
        rows.append(number_buttons[:3])
        if len(number_buttons) > 3:
            rows.append(number_buttons[3:5])
    if has_more:
        rows.append([_button(BUTTON_MORE_PARTNERS, "partners_more")])
    rows.append([_button(BUTTON_CHANGE_CITY, "city_select")])
    rows.append([_button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_empty_catalog_keyboard() -> str:
    return _keyboard([[_button(BUTTON_CHANGE_CITY, "city_select", "primary")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_partners_keyboard(partners: list[dict], category: str | None = None) -> str:
    return get_partner_catalog_keyboard(len(partners), has_more=len(partners) > PARTNERS_PAGE_SIZE)


def get_partner_card_keyboard(partner_id: int | str | None = None, web_url: object = None) -> str:
    rows = [[_button(BUTTON_GET_CODE, "web_get_privilege", "positive", partner_id=partner_id)]]
    if is_valid_open_link_url(web_url):
        rows.append([_url_button(BUTTON_OPEN_SITE, str(web_url))])
    rows.extend(
        [
            [_button(BUTTON_BACK_TO_PARTNERS, "partners")],
            [_button(BUTTON_CHANGE_CITY, "city_select")],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )
    return _keyboard(rows)


def get_partner_actions_keyboard(partner_id: int, has_contacts: bool = False) -> str:
    return get_partner_card_keyboard(partner_id)


def get_web_partner_actions_keyboard(partner_id: int) -> str:
    return get_partner_card_keyboard(partner_id)


def get_web_offers_keyboard(partner_id: int, offers: list[dict]) -> str:
    return get_partner_card_keyboard(partner_id)


def get_privilege_success_keyboard(partner_id: int | str | None = None) -> str:
    return _keyboard(
        [
            [_button(BUTTON_MY_CODES, "my_codes", "primary")],
            [_button(BUTTON_BACK_TO_PARTNER, "partner_selected", partner_id=partner_id)],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_privilege_no_subscription_keyboard() -> str:
    return _keyboard([[_button(BUTTON_PAY, "pay", "positive")], [_button(BUTTON_BACK_TO_PARTNERS, "partners")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_stale_catalog_keyboard() -> str:
    return _keyboard([[_button(BUTTON_PARTNERS, "partners", "primary")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_services_keyboard(partner_id: int, services: list[dict]) -> str:
    rows = [
        [_button(str(service.get("title") or f"Предложение {service.get('id')}"), "service_selected", service_id=service.get("id"), partner_id=partner_id)]
        for service in services[:3]
    ]
    rows.append([_button("Назад", "back"), _button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_service_actions_keyboard(partner_id: int, service_id: int) -> str:
    return _keyboard(
        [
            [_button("Получить привилегию", "get_discount_code", "positive", partner_id=partner_id, service_id=service_id)],
            [_button("Назад", "back"), _button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_codes_filter_keyboard() -> str:
    return _keyboard(
        [
            [_button("Активные", "codes_filter", "primary", status="active"), _button("Все", "codes_filter", status="all")],
            [_button("Использованные", "codes_filter", status="used"), _button("Истёкшие", "codes_filter", status="expired")],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_payment_request_keyboard() -> str:
    return _keyboard([[_button("✅ Я оплатил", "payment_paid", "positive")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_no_subscription_keyboard() -> str:
    return get_privilege_no_subscription_keyboard()


def get_backend_unavailable_keyboard() -> str:
    return get_nav_keyboard()


def get_verify_success_keyboard() -> str:
    return get_main_keyboard()


def get_verify_error_keyboard() -> str:
    return get_nav_keyboard()


def get_admin_keyboard() -> str:
    return _keyboard([[_button("/debug", "debug"), _button("/health", "health")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_service_search_results_keyboard(results: list[dict]) -> str:
    rows = [
        [_button(str(item.get("service_title") or f"Предложение {item.get('service_id')}"), "service_selected", partner_id=item.get("partner_id"), service_id=item.get("service_id"))]
        for item in results[:3]
    ]
    rows.append([_button("Новый поиск", "service_search_start"), _button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)
