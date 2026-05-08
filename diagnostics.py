def format_debug_status(config, user_state_size: int = 0, legacy_admin_enabled: bool = False, legacy_scheduler_enabled: bool = False) -> str:
    return "\n".join(
        [
            "Debug status",
            f"backend_mode={config.vk_bot_use_backend}",
            f"backend_base_url={config.backend_base_url}",
            f"user_state_size={user_state_size}",
            f"legacy_admin_enabled={legacy_admin_enabled}",
            f"legacy_scheduler_enabled={legacy_scheduler_enabled}",
        ]
    )


def format_health_status(config, gateway=None) -> str:
    if gateway is None:
        return "Health: legacy mode"
    try:
        gateway.health()
    except Exception:
        return "Health: backend_unavailable"
    return "Health: ok"
