import json
from typing import Iterable

BUTTON_SUBSCRIPTION = "💗 Подписка"
BUTTON_JOIN_CLUB = "💗 Присоединиться к клубу"
BUTTON_PARTNERS = "✨ Партнёры и скидки"
BUTTON_MY_CODES = "🎁 Мои привилегии"
BUTTON_PAY = "💳 Оплатить / Продлить"
BUTTON_CITY = "🌸 Выбрать город"
BUTTON_HELP = "❓ Помощь"
BUTTON_MAIN_MENU = "🏠 Главное меню"

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


def _keyboard(rows: Iterable[Iterable[dict]], one_time: bool = False) -> str:
    return json.dumps(
        {"one_time": one_time, "inline": False, "buttons": [list(row) for row in rows]},
        ensure_ascii=False,
    )


def get_main_keyboard() -> str:
    return _keyboard(
        [
            [_button(BUTTON_JOIN_CLUB, "join_club", "primary")],
            [_button(BUTTON_SUBSCRIPTION, "subscription", "primary")],
            [_button(BUTTON_PARTNERS, "partners", "primary")],
            [_button(BUTTON_MY_CODES, "my_codes"), _button(BUTTON_PAY, "pay", "positive")],
            [_button(BUTTON_CITY, "city_select"), _button(BUTTON_HELP, "help")],
        ]
    )


def get_nav_keyboard() -> str:
    return _keyboard([[_button(BUTTON_MAIN_MENU, "main_menu", "primary")]])


def get_city_keyboard() -> str:
    rows = [[_button(city, "city_selected", "primary", city=city)] for city in CITIES]
    rows.append([_button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_city_selected_keyboard() -> str:
    return _keyboard(
        [
            [_button(BUTTON_PARTNERS, "partners", "primary")],
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_categories_keyboard(categories: list[str] | None = None) -> str:
    category_names = categories or WOMEN_CATEGORIES
    rows = [[_button("Все категории", "category_selected", "primary", category="all")]]
    rows.extend([[_button(name, "category_selected", category=name)] for name in category_names])
    rows.append([_button("Найти предложение", "service_search_start", "primary")])
    rows.append([_button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_partners_keyboard(partners: list[dict], category: str | None = None) -> str:
    rows = [
        [_button(str(partner.get("name") or f"Партнёр {partner.get('id')}"), "partner_selected", partner_id=partner.get("id"))]
        for partner in partners
    ]
    rows.append([_button("Назад", "back"), _button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_partner_actions_keyboard(partner_id: int, has_contacts: bool = False) -> str:
    rows = [[_button("Услуги и предложения", "partner_services", "primary", partner_id=partner_id)]]
    if has_contacts:
        rows.append([_button("Контакты", "partner_contacts", partner_id=partner_id)])
    rows.append([_button("Назад", "back"), _button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)


def get_services_keyboard(partner_id: int, services: list[dict]) -> str:
    rows = [
        [_button(str(service.get("title") or f"Предложение {service.get('id')}"), "service_selected", service_id=service.get("id"), partner_id=partner_id)]
        for service in services
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
            [_button(BUTTON_MAIN_MENU, "main_menu")],
        ]
    )


def get_payment_request_keyboard() -> str:
    return _keyboard([[_button("✅ Я оплатил", "payment_paid", "positive")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


def get_no_subscription_keyboard() -> str:
    return _keyboard([[_button(BUTTON_PAY, "pay", "positive")], [_button(BUTTON_MAIN_MENU, "main_menu")]])


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
        for item in results
    ]
    rows.append([_button("Новый поиск", "service_search_start"), _button(BUTTON_MAIN_MENU, "main_menu")])
    return _keyboard(rows)
