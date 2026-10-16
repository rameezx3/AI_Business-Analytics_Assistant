"""Role checks for local application accounts."""

from datetime import datetime, timedelta, timezone

from utils import access_control


def test_anonymous_session_has_no_account_or_admin_access(monkeypatch):
    state = {}
    monkeypatch.setattr(access_control.st, "session_state", state)
    assert access_control.current_account() is None
    assert not access_control.is_logged_in()
    assert not access_control.has_admin_access()


def test_user_session_is_authenticated_but_not_admin(monkeypatch):
    state = {"app_user": {
        "email": "user@example.com", "role": "user",
        "authenticated_at": datetime.now(timezone.utc).isoformat(),
    }}
    monkeypatch.setattr(access_control.st, "session_state", state)
    assert access_control.is_logged_in()
    assert not access_control.has_admin_access()


def test_admin_session_has_admin_access(monkeypatch):
    state = {"app_user": {
        "email": "admin@example.com", "role": "admin",
        "authenticated_at": datetime.now(timezone.utc).isoformat(),
    }}
    monkeypatch.setattr(access_control.st, "session_state", state)
    assert access_control.has_admin_access()


def test_expired_session_is_removed(monkeypatch):
    state = {"app_user": {
        "email": "admin@example.com", "role": "admin",
        "authenticated_at": (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat(),
    }}
    monkeypatch.setattr(access_control.st, "session_state", state)
    assert access_control.current_account() is None
    assert "app_user" not in state


def test_invalid_role_or_timestamp_fails_closed(monkeypatch):
    state = {"app_user": {
        "email": "admin@example.com", "role": "superuser", "authenticated_at": "bad",
    }}
    monkeypatch.setattr(access_control.st, "session_state", state)
    assert not access_control.has_admin_access()
