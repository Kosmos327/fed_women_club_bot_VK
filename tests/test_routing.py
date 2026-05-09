from routing import parse_code_command, parse_link_code_command, parse_partner_command, parse_service_command, parse_verify_partner_command


def test_parse_commands():
    assert parse_partner_command("Партнёр 12") == 12
    assert parse_service_command("Услуга 34") == 34
    assert parse_code_command("Код 56") == 56
    assert parse_verify_partner_command("verify_partner_78") == 78


def test_parse_link_code_command_recognizes_russian_command():
    assert parse_link_code_command("Привязать ABC12345") == "ABC12345"


def test_parse_link_code_command_recognizes_link_command():
    assert parse_link_code_command("link ABC12345") == "ABC12345"


def test_parse_link_code_command_rejects_unrelated_text():
    assert parse_link_code_command("покажи партнёров ABC12345") is None
    assert parse_link_code_command("ABC12345") is None


def test_join_club_text_phrase_is_routed_by_main_handler_source():
    source = open("main.py", encoding="utf-8").read()

    assert 'action == "join_club"' in source
    assert '"присоединиться к клубу" in text' in source
