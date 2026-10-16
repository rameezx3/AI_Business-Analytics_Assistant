"""Local email/password authentication with salted PBKDF2 hashes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.connection import db
from database.models.app_user import AppUser


HASH_NAME = "pbkdf2_sha256"
HASH_ROUNDS = 600_000
SALT_BYTES = 16
KEY_BYTES = 32
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 12
_DUMMY_HASH = "pbkdf2_sha256$600000$MDEyMzQ1Njc4OWFiY2RlZg==$WOBI2s4fIPqZfBZL5Gx6H9mB6hZ7EwMbCWp2TQnKFrU="


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)) and len(email) <= 254


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ROUNDS, dklen=KEY_BYTES)
    import base64
    return f"{HASH_NAME}${HASH_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        import base64
        algorithm, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != HASH_NAME:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def ensure_account_table() -> None:
    """Create only the account table when needed; leave all existing data intact."""
    AppUser.__table__.create(db.engine, checkfirst=True)


def create_user_account(email: str, password: str) -> tuple[bool, str]:
    email = normalize_email(email)
    if not valid_email(email):
        return False, "Enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Choose a password with at least {MIN_PASSWORD_LENGTH} characters."
    ensure_account_table()
    try:
        with db.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO app_users (email, role, password_hash, is_active, failed_attempts)
                VALUES (:email, 'user', :password_hash, TRUE, 0)
            """), {"email": email, "password_hash": hash_password(password)})
    except IntegrityError:
        return False, "An account with that email already exists. Sign in instead."
    return True, "Account created. Sign in to continue."


def create_admin_account(email: str, password: str) -> tuple[bool, str]:
    """Create an admin from the owner-only setup CLI, never from public sign-up."""
    email = normalize_email(email)
    if not valid_email(email):
        return False, "Enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Choose a password with at least {MIN_PASSWORD_LENGTH} characters."
    ensure_account_table()
    try:
        with db.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO app_users (email, role, password_hash, is_active, failed_attempts)
                VALUES (:email, 'admin', :password_hash, TRUE, 0)
            """), {"email": email, "password_hash": hash_password(password)})
    except IntegrityError:
        return False, "An account with that email already exists."
    return True, "Administrator account created."


def authenticate_account(email: str, password: str, requested_role: str) -> dict | None:
    email = normalize_email(email)
    role = requested_role.strip().lower()
    if role not in {"admin", "user"}:
        return None
    ensure_account_table()
    now = datetime.now(timezone.utc)
    with db.engine.begin() as connection:
        row = connection.execute(text("""
            SELECT email, role, password_hash, is_active, failed_attempts, locked_until
            FROM app_users
            WHERE email = :email AND role = :role
            FOR UPDATE
        """), {"email": email, "role": role}).mappings().first()

        if row is None:
            verify_password(password, _DUMMY_HASH)
            return None
        if not row["is_active"]:
            verify_password(password, row["password_hash"])
            return None
        locked_until = row["locked_until"]
        if locked_until is not None and locked_until > now:
            verify_password(password, row["password_hash"])
            return None

        if verify_password(password, row["password_hash"]):
            connection.execute(text("""
                UPDATE app_users SET failed_attempts = 0, locked_until = NULL
                WHERE email = :email
            """), {"email": email})
            return {"email": row["email"], "role": row["role"]}

        attempts = 0 if locked_until is not None and locked_until <= now else int(row["failed_attempts"])
        attempts += 1
        lock = now + timedelta(minutes=LOCKOUT_MINUTES) if attempts >= MAX_FAILED_ATTEMPTS else None
        connection.execute(text("""
            UPDATE app_users SET failed_attempts = :attempts, locked_until = :locked_until
            WHERE email = :email
        """), {"email": email, "attempts": attempts, "locked_until": lock})
    return None
