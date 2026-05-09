WEB_KNOWN_CITY_SLUGS = {
    "новосибирск": "novosibirsk",
    "череповец": "cherepovets",
}


def get_web_known_city_slug(selected_city: str | None) -> str | None:
    if not selected_city:
        return None
    return WEB_KNOWN_CITY_SLUGS.get(selected_city.strip().lower())
