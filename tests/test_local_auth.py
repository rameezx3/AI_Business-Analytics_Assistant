"""Local password hashing and credential-validation checks."""

from services.local_auth import hash_password, normalize_email, valid_email, verify_password


def test_password_is_salted_and_verifiable():
    first = hash_password("a-long-demo-password")
    second = hash_password("a-long-demo-password")
    assert first != second
    assert verify_password("a-long-demo-password", first)
    assert not verify_password("incorrect-password", first)


def test_email_normalization_and_validation():
    assert normalize_email("  User@Example.COM ") == "user@example.com"
    assert valid_email("User@Example.COM")
    assert not valid_email("not-an-email")
