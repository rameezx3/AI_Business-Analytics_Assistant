"""Session helpers for local Admin/User accounts."""

from datetime import datetime, timedelta, timezone

import streamlit as st


SESSION_MAX_AGE = timedelta(hours=8)


def current_account() -> dict | None:
    account = st.session_state.get("app_user")
    if not isinstance(account, dict) or account.get("role") not in {"admin", "user"}:
        return None
    try:
        signed_in = datetime.fromisoformat(account["authenticated_at"])
        if signed_in.tzinfo is None:
            signed_in = signed_in.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - signed_in > SESSION_MAX_AGE:
            st.session_state.pop("app_user", None)
            return None
    except (KeyError, TypeError, ValueError):
        st.session_state.pop("app_user", None)
        return None
    if not isinstance(account.get("email"), str):
        st.session_state.pop("app_user", None)
        return None
    return account


def is_logged_in() -> bool:
    return current_account() is not None


def has_admin_access(*_args, **_kwargs) -> bool:
    """Admin access is granted only to an authenticated admin session."""
    account = current_account()
    return bool(account and account["role"] == "admin")
