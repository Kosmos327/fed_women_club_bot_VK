import re


def _parse_id(pattern: str, text: str | None) -> int | None:
    if not text:
        return None
    match = re.fullmatch(pattern, text.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def parse_partner_command(text: str | None) -> int | None:
    return _parse_id(r"партн[её]р\s+(\d+)", text)


def parse_service_command(text: str | None) -> int | None:
    return _parse_id(r"услуга\s+(\d+)", text)


def parse_code_command(text: str | None) -> int | None:
    return _parse_id(r"код\s+(\d+)", text)


def is_legacy_discount_command(text: str | None) -> bool:
    return bool(text and re.fullmatch(r"скидка\s+\d+", text.strip(), flags=re.IGNORECASE))


def is_legacy_confirm_command(text: str | None) -> bool:
    return bool(text and re.fullmatch(r"да\s+\d+", text.strip(), flags=re.IGNORECASE))
