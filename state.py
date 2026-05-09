USER_STATE: dict[int, dict] = {}

WEB_SESSION_KEYS = ("web_client_token", "web_client_user", "web_linked_at", "web_link_status")


def get_user_state(user_id: int) -> dict:
    return USER_STATE.setdefault(user_id, {})


def set_web_client_session(vk_user_id: int | str, token: str, user: dict | None = None, linked_at: str | None = None) -> None:
    state = get_user_state(int(vk_user_id))
    state["web_client_token"] = token
    state["web_client_user"] = user or {}
    if linked_at:
        state["web_linked_at"] = linked_at
    state["web_link_status"] = "active"


def get_web_client_token(vk_user_id: int | str) -> str | None:
    token = get_user_state(int(vk_user_id)).get("web_client_token")
    return str(token) if token else None


def clear_web_client_session(vk_user_id: int | str) -> None:
    state = get_user_state(int(vk_user_id))
    for key in WEB_SESSION_KEYS:
        state.pop(key, None)


def clear_user_flow_state(user_id: int) -> None:
    state = get_user_state(user_id)
    preserved = {key: state.get(key) for key in ("selected_city", *WEB_SESSION_KEYS) if state.get(key)}
    state.clear()
    state.update(preserved)


def reset_user_state(user_id: int) -> None:
    USER_STATE.pop(user_id, None)
