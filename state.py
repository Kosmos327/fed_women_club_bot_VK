USER_STATE: dict[int, dict] = {}


def get_user_state(user_id: int) -> dict:
    return USER_STATE.setdefault(user_id, {})


def clear_user_flow_state(user_id: int) -> None:
    state = get_user_state(user_id)
    selected_city = state.get("selected_city")
    state.clear()
    if selected_city:
        state["selected_city"] = selected_city


def reset_user_state(user_id: int) -> None:
    USER_STATE.pop(user_id, None)
