from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hashing_is_not_reversible():
    encoded = hash_password("StrongPass123!")
    assert encoded != "StrongPass123!"
    assert verify_password("StrongPass123!", encoded)
    assert not verify_password("wrong-password", encoded)


def test_jwt_contains_subject_and_expiration():
    token = create_access_token("42")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload
