"""Unit tests for ChangePasswordRequest schema."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import ChangePasswordRequest


class TestChangePasswordRequest:
    def test_accepts_valid_payload(self) -> None:
        req = ChangePasswordRequest(
            current_password="oldPass1", new_password="newPass1!"
        )
        assert req.current_password == "oldPass1"
        assert req.new_password == "newPass1!"

    def test_rejects_empty_current(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="", new_password="newPass1!")

    def test_rejects_short_new_password(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="oldPass1", new_password="short1"
            )

    def test_rejects_new_password_without_digit(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ChangePasswordRequest(
                current_password="oldPass1", new_password="abcdefgh"
            )
        assert "digit" in str(exc.value).lower()

    def test_rejects_new_password_over_128_chars(self) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="oldPass1", new_password="a1" * 65
            )
