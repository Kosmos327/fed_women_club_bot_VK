import json

import keyboards

from keyboards import (
    BUTTON_MAIN_MENU,
    BUTTON_PASSWORD_SETUP,
    BUTTON_WEB_LOGIN,
    WOMEN_CATEGORIES,
    get_categories_keyboard,
    get_city_keyboard,
    get_main_keyboard,
    get_codes_filter_keyboard,
    get_password_setup_keyboard,
    get_profile_survey_city_keyboard,
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
    assert labels == ["Все категории", "Красота", "Маникюр / педикюр", "Сменить город", "🏠 Главное меню"]
    assert len(json.loads(get_categories_keyboard())["buttons"]) <= 5


def test_city_keyboard_is_compact_for_vk_limits():
    labels = _labels(get_city_keyboard())

    assert labels == ["Новосибирск", "Другой город", "Назад в меню"]
    assert len(json.loads(get_city_keyboard())["buttons"]) <= 5


def test_profile_survey_city_keyboard_uses_web_city_rows_and_respects_vk_row_limit():
    labels = _labels(
        get_profile_survey_city_keyboard(
            [
                {"name": "Новосибирск", "slug": "novosibirsk"},
                {"name": "Череповец", "slug": "cherepovets"},
                {"name": "Томск", "slug": "tomsk"},
                {"name": "Казань", "slug": "kazan"},
            ]
        )
    )

    assert labels == ["Новосибирск", "Череповец", "Томск", "Другой город", "Пропустить", BUTTON_MAIN_MENU]
    assert _row_count(
        get_profile_survey_city_keyboard(
            [
                {"name": "Новосибирск", "slug": "novosibirsk"},
                {"name": "Череповец", "slug": "cherepovets"},
                {"name": "Томск", "slug": "tomsk"},
                {"name": "Казань", "slug": "kazan"},
            ]
        )
    ) <= 5


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


def test_web_onboarding_keyboard_adds_login_and_password_setup_buttons():
    web_login_url = "https://bloomclub.ru/login"
    setup_url = "https://bloomclub.ru/password/setup?token=one-time-token"

    actions = _actions(get_web_onboarding_keyboard(password_setup_url=setup_url, web_login_url=web_login_url))

    assert actions[0] == {"type": "open_link", "label": BUTTON_WEB_LOGIN, "link": web_login_url}
    assert actions[1] == {"type": "open_link", "label": BUTTON_PASSWORD_SETUP, "link": setup_url}


def test_web_onboarding_keyboard_skips_invalid_web_login_url():
    keyboard = get_web_onboarding_keyboard(web_login_url="ftp://bloomclub.ru/login")

    assert _labels(keyboard) == _labels(get_main_keyboard())
    assert all(action["type"] == "text" for action in _actions(keyboard))


def _row_count(keyboard_json: str) -> int:
    return len(json.loads(keyboard_json)["buttons"])


def test_my_privileges_keyboard_contains_all_filters_and_keeps_vk_row_limit():
    keyboard = json.loads(get_codes_filter_keyboard())

    assert [[button["action"]["label"] for button in row] for row in keyboard["buttons"]] == [
        ["Активные", "Все"],
        ["Использованные", "Истёкшие"],
        [BUTTON_MAIN_MENU],
    ]
    assert _row_count(get_codes_filter_keyboard()) <= 5


def test_vk_keyboard_builders_keep_safe_row_limit():
    assert _row_count(get_main_keyboard()) <= 5
    assert _row_count(get_city_keyboard()) <= 5
    assert _row_count(keyboards.get_partner_catalog_keyboard(5, has_more=True)) <= 5
    assert _row_count(keyboards.get_partner_card_keyboard(1, "https://example.com")) <= 5
    assert _row_count(keyboards.get_empty_catalog_keyboard()) <= 5
    assert _row_count(keyboards.get_safe_fallback_keyboard()) <= 5
    assert _row_count(get_codes_filter_keyboard()) <= 5
