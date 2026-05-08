from routing import parse_code_command, parse_partner_command, parse_service_command


def test_parse_commands():
    assert parse_partner_command("Партнёр 12") == 12
    assert parse_service_command("Услуга 34") == 34
    assert parse_code_command("Код 56") == 56
