import json

from keyboards import (
    BUTTON_PASSWORD_SETUP,
    BUTTON_WEB_LOGIN,
    CITIES,
    WOMEN_CATEGORIES,
    get_categories_keyboard,
    get_city_keyboard,
    get_main_keyboard,
    get_password_setup_keyboard,
    get_web_onboarding_keyboard,
)


def _labels(keyboard_json: str) -> list[str]:
    keyboard = json.loads(keyboard_json)
    return [button["action"]["label"] for row in keyboard["buttons"] for button in row]


def test_main_keyboard_contains_women_club_buttons():
    labels = _labels(get_main_keyboard())

    assert labels == [
        "💗 Присоединиться к клубу",
        "💗 Подписка",
        "✨ Партнёры и скидки",
        "🎁 Мои привилегии",
        "💳 Оплатить / Продлить",
        "🌸 Выбрать город",
        "❓ Помощь",
    ]


def test_categories_match_women_club_list():
    labels = _labels(get_categories_keyboard())

    assert WOMEN_CATEGORIES == [
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
    for category in WOMEN_CATEGORIES:
        assert category in labels


def test_city_keyboard_contains_five_mvp_cities():
    labels = _labels(get_city_keyboard())

    assert CITIES == ["Новосибирск", "Москва", "Санкт-Петербург", "Екатеринбург", "Казань"]
    for city in CITIES:
        assert city in labels


def _actions(keyboard_json: str) -> list[dict]:
    keyboard = json.loads(keyboard_json)
    return [button["action"] for row in keyboard["buttons"] for button in row]


def test_password_setup_keyboard_adds_vk_open_link_button_for_valid_url():
    setup_url = "https://bloomclub.ru/password/setup?token=one-time-token"

    actions = _actions(get_password_setup_keyboard(setup_url))

    assert actions[0] == {"type": "open_link", "label": BUTTON_PASSWORD_SETUP, "link": setup_url}
    assert "💗 Присоединиться к клубу" in [action["label"] for action in actions]


def test_password_setup_keyboard_skips_invalid_url_and_keeps_menu_buttons():
    password_keyboard = get_password_setup_keyboard("javascript:alert(1)")

    assert _labels(password_keyboard) == _labels(get_main_keyboard())
    assert all(action["type"] == "text" for action in _actions(password_keyboard))


def test_web_onboarding_keyboard_adds_web_login_button_for_valid_url():
    web_login_url = "https://bloomclub.ru/login?login=user%40example.com"

    actions = _actions(get_web_onboarding_keyboard(web_login_url=web_login_url))

    assert actions[0] == {"type": "open_link", "label": BUTTON_WEB_LOGIN, "link": web_login_url}
    assert "💗 Присоединиться к клубу" in [action["label"] for action in actions]


def test_web_onboarding_keyboard_skips_invalid_web_login_url():
    keyboard = get_web_onboarding_keyboard(web_login_url="ftp://bloomclub.ru/login")

    assert _labels(keyboard) == _labels(get_main_keyboard())
    assert all(action["type"] == "text" for action in _actions(keyboard))
