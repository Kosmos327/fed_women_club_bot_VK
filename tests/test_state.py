from state import clear_web_client_session, get_user_state, get_web_client_token, reset_user_state, set_web_client_session


def test_web_client_session_helpers_set_get_and_clear_token():
    reset_user_state(1001)

    set_web_client_session(1001, "client-token", {"email": "user@example.com"}, linked_at="2026-05-09T00:00:00")

    assert get_web_client_token(1001) == "client-token"
    assert get_user_state(1001)["web_client_user"] == {"email": "user@example.com"}
    assert get_user_state(1001)["web_link_status"] == "active"

    clear_web_client_session(1001)

    assert get_web_client_token(1001) is None
    assert "web_client_user" not in get_user_state(1001)
