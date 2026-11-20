"""Hash password dan token sesi (T5.1), tanpa database."""

import asyncio

import pytest

from app.core.security import (
    PasswordPolicyError,
    check_password_policy,
    hash_password,
    hash_password_async,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
    verify_password_async,
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


async def test_hash_tidak_menahan_event_loop() -> None:
    """Satu hash ~100 ms. Delapan serentak tidak boleh membekukan coroutine lain."""
    stored = hash_password(PASSWORD)
    jeda_terbesar = 0.0

    async def detak() -> None:
        nonlocal jeda_terbesar
        loop = asyncio.get_running_loop()
        for _ in range(30):
            mulai = loop.time()
            await asyncio.sleep(0.01)
            jeda_terbesar = max(jeda_terbesar, loop.time() - mulai - 0.01)

    hasil = await asyncio.gather(
        *(verify_password_async(PASSWORD, stored) for _ in range(8)), detak()
    )
    assert all(hasil[:8])
    assert jeda_terbesar < 0.05, f"event loop tertahan {jeda_terbesar:.3f} detik"


async def test_banjir_login_tidak_menghabiskan_thread_bawaan() -> None:
    """Hash yang mengantre menunggu di event loop, bukan memegang thread bawaan.

    FastAPI menjalankan dependensi sinkron (misalnya get_settings) di pool thread
    bawaan anyio (40 thread). Delapan puluh verifikasi serentak tidak boleh
    membuat pekerjaan sinkron lain menunggu giliran thread.
    """
    from starlette.concurrency import run_in_threadpool

    stored = hash_password(PASSWORD)
    verifikasi = [asyncio.create_task(verify_password_async(PASSWORD, stored)) for _ in range(80)]
    await asyncio.sleep(0.05)  # biarkan antrean terbentuk
    loop = asyncio.get_running_loop()
    mulai = loop.time()
    assert await run_in_threadpool(lambda: 1) == 1
    lama = loop.time() - mulai
    for tugas in verifikasi:
        tugas.cancel()
    await asyncio.gather(*verifikasi, return_exceptions=True)
    assert lama < 0.2, f"pekerjaan sinkron menunggu thread {lama:.3f} detik"


async def test_hash_async_sama_dengan_sinkron() -> None:
    stored = await hash_password_async(PASSWORD)
    assert verify_password(PASSWORD, stored)
    assert not await verify_password_async("salah", stored)


def test_token_sesi_acak_dan_hanya_hash_yang_disimpan() -> None:
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) >= 40
    assert hash_session_token(a) != a and len(hash_session_token(a)) == 64
    assert hash_session_token(a) == hash_session_token(a)
