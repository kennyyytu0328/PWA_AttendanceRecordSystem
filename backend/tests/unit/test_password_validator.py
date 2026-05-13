"""Unit tests for password-strength validator."""

import pytest

from app.utils.password import validate_password_strength


class TestValidatePasswordStrength:
    def test_accepts_8_chars_with_digit(self) -> None:
        validate_password_strength("abcdefg1")  # no raise

    def test_accepts_128_char_max(self) -> None:
        validate_password_strength("a1" * 64)  # exactly 128 chars

    def test_rejects_too_short(self) -> None:
        with pytest.raises(ValueError, match="at least 8"):
            validate_password_strength("abc1")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="at least 8"):
            validate_password_strength("")

    def test_rejects_no_digit(self) -> None:
        with pytest.raises(ValueError, match="digit"):
            validate_password_strength("abcdefgh")

    def test_rejects_over_128_chars(self) -> None:
        with pytest.raises(ValueError, match="at most 128"):
            validate_password_strength("a1" * 65)  # 130 chars
