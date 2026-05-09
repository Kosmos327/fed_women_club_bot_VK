import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    vk_group_token: str
    vk_group_id: int
    admin_id: int
    club_invite_link: str
    backend_base_url: str
    bot_api_token: str
    vk_bot_use_backend: bool
    web_api_base_url: str
    web_api_timeout_seconds: int


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


def _get_bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    use_backend = _get_bool_env("VK_BOT_USE_BACKEND", default=True)
    vk_group_token = _get_required_env("VK_GROUP_TOKEN")
    vk_group_id = int(_get_required_env("VK_GROUP_ID"))
    admin_id = int(_get_required_env("ADMIN_ID"))
    backend_base_url = os.getenv(
        "BACKEND_BASE_URL",
        "https://women-club.example/api/v1",
    ).strip()
    bot_api_token = os.getenv("BOT_API_TOKEN", "").strip()
    web_api_base_url = os.getenv("WEB_API_BASE_URL", "https://bloomclub.ru").strip()
    web_api_timeout_seconds = int(os.getenv("WEB_API_TIMEOUT_SECONDS", "10").strip() or "10")

    if use_backend:
        if not backend_base_url:
            raise ValueError(
                "VK_BOT_USE_BACKEND=true: не задана переменная окружения BACKEND_BASE_URL"
            )
        if not bot_api_token:
            raise ValueError(
                "VK_BOT_USE_BACKEND=true: не задана переменная окружения BOT_API_TOKEN"
            )

    return Config(
        vk_group_token=vk_group_token,
        vk_group_id=vk_group_id,
        admin_id=admin_id,
        club_invite_link=os.getenv("CLUB_INVITE_LINK", "").strip(),
        backend_base_url=backend_base_url,
        bot_api_token=bot_api_token,
        vk_bot_use_backend=use_backend,
        web_api_base_url=web_api_base_url,
        web_api_timeout_seconds=web_api_timeout_seconds,
    )
