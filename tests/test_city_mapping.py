from city_mapping import get_web_known_city_slug


def test_city_mapping_returns_novosibirsk_for_novosibirsk():
    assert get_web_known_city_slug("Новосибирск") == "novosibirsk"


def test_city_mapping_returns_cherepovets_for_cherepovets():
    assert get_web_known_city_slug("Череповец") == "cherepovets"


def test_city_mapping_returns_none_for_not_web_known_cities():
    assert get_web_known_city_slug("Москва") is None
    assert get_web_known_city_slug("Неизвестный город") is None
