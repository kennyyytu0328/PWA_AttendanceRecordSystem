from app.utils.password import hash_password, verify_password


class TestHashPassword:
    def test_hash_password_returns_string(self) -> None:
        result = hash_password("mysecretpassword")
        assert isinstance(result, str)

    def test_hash_password_not_plaintext(self) -> None:
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_hash_determinism(self) -> None:
        """Two hashes of the same password must differ due to random salt."""
        plain = "mysecretpassword"
        hash_a = hash_password(plain)
        hash_b = hash_password(plain)
        assert hash_a != hash_b


class TestVerifyPassword:
    def test_verify_correct_password(self) -> None:
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False
