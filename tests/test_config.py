import pytest

from config import load_config


def test_load_config_uses_safe_placeholder_backend_url(monkeypatch):
    monkeypatch.setenv("VK_GROUP_TOKEN", "test-token")
    monkeypatch.setenv("VK_GROUP_ID", "123")
    monkeypatch.setenv("ADMIN_ID", "456")
    monkeypatch.setenv("BOT_API_TOKEN", "test-api-token")
    monkeypatch.delenv("BACKEND_BASE_URL", raising=False)

    config = load_config()

    assert config.backend_base_url == "https://women-club.example/api/v1"
    assert config.vk_bot_use_backend is True


def test_load_config_requires_bot_api_token_in_backend_mode(monkeypatch):
    monkeypatch.setenv("VK_GROUP_TOKEN", "test-token")
    monkeypatch.setenv("VK_GROUP_ID", "123")
    monkeypatch.setenv("ADMIN_ID", "456")
    monkeypatch.delenv("BOT_API_TOKEN", raising=False)

    with pytest.raises(ValueError, match="BOT_API_TOKEN"):
        load_config()
