import json

from keyboards import CITIES, WOMEN_CATEGORIES, get_categories_keyboard, get_city_keyboard, get_main_keyboard


def _labels(keyboard_json: str) -> list[str]:
    keyboard = json.loads(keyboard_json)
    return [button["action"]["label"] for row in keyboard["buttons"] for button in row]


def test_main_keyboard_contains_women_club_buttons():
    labels = _labels(get_main_keyboard())

    assert labels == [
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
