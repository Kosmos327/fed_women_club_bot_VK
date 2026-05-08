import json

from keyboards import BUTTON_PARTNERS, get_main_keyboard


def test_main_keyboard_contains_partners_button():
    keyboard = json.loads(get_main_keyboard())

    labels = [button["action"]["label"] for row in keyboard["buttons"] for button in row]

    assert BUTTON_PARTNERS in labels
