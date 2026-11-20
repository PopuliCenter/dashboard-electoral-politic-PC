"""Hash password dan token sesi (T5.1), tanpa database."""

import pytest

from app.core.security import (
    PasswordPolicyError,
    check_password_policy,
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)

PASSWORD = "kata-sandi-uji-panjang"


def test_hash_dan_verifikasi() -> None:
    stored = hash_password(PASSWORD)
    assert stored.startswith("scrypt$")
    assert PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password(PASSWORD + "x", stored)


def test_salt_acak_membuat_hash_berbeda() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


@pytest.mark.parametrize(
    "stored",
    ["", "plaintext", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$32768$8$1$!!$!!"],
)
def test_format_tidak_dikenal_dianggap_salah(stored: str) -> None:
    assert verify_password(PASSWORD, stored) is False


def test_perlu_hash_ulang_bila_parameter_berubah() -> None:
    assert not needs_rehash(hash_password(PASSWORD))
    assert needs_rehash("scrypt$16384$8$1$AAAA$AAAA")


@pytest.mark.parametrize("password", ["pendek", "x" * 257])
def test_kebijakan_panjang_password(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        check_password_policy(password)


def test_token_sesi_acak_dan_hanya_hash_yang_disimpan() -> None:
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) >= 40
    assert hash_session_token(a) != a and len(hash_session_token(a)) == 64
    assert hash_session_token(a) == hash_session_token(a)
