"""Hash password dan token sesi (T5.1). Hanya pustaka standar Python.

Password di-hash dengan scrypt (memory-hard) dari `hashlib`, sehingga tidak
perlu dependensi tambahan. Format tersimpan:

    scrypt$<n>$<r>$<p>$<salt base64>$<hash base64>

Parameter ikut tersimpan, jadi parameter bisa dinaikkan kelak tanpa membuat
hash lama tidak terbaca; `needs_rehash` memberi tahu kapan hash perlu diganti.
"""

import base64
import hashlib
import hmac
import secrets
import threading

from starlette.concurrency import run_in_threadpool

# n=2**15, r=8: sekitar 32 MiB memori dan ~100 ms per hash (diukur di kontainer
# api). Cukup lambat untuk menyulitkan tebakan massal; karena itu hash TIDAK
# boleh dijalankan langsung di event loop (lihat verify_password_async).
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
HASH_BYTES = 32
# scrypt butuh 128 * n * r byte; batas bawaan OpenSSL 32 MiB pas di ambang.
_MAXMEM = 64 * 1024 * 1024

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class PasswordPolicyError(ValueError):
    pass


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password minimal {MIN_PASSWORD_LENGTH} karakter")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password maksimal {MAX_PASSWORD_LENGTH} karakter")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=_MAXMEM
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, HASH_BYTES)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Waktu-konstan terhadap isi hash. Format yang tidak dikenal = salah."""
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        actual = _scrypt(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    parts = stored.split("$")
    return len(parts) != 6 or parts[:4] != [
        "scrypt",
        str(SCRYPT_N),
        str(SCRYPT_R),
        str(SCRYPT_P),
    ]


# Hash password acak, dipakai untuk menyamakan waktu respons login saat email
# tidak terdaftar: tanpa ini, respons cepat membocorkan email mana yang ada.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def new_session_token() -> str:
    """Token sesi acak 256 bit untuk cookie."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 token; hanya ini yang disimpan di database."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


# --------------------------------------------------------------------------- #
# Versi async: hash di thread, dengan jumlah serentak dibatasi
# --------------------------------------------------------------------------- #

# Tiap hash ~32 MiB; empat serentak = ~128 MiB, aman untuk server 8 GB. Antrean
# menunggu di thread pool, bukan di event loop, jadi endpoint lain tetap jalan.
MAX_CONCURRENT_HASHES = 4
_HASH_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_HASHES)


def _verify_limited(password: str, stored: str) -> bool:
    with _HASH_SLOTS:
        return verify_password(password, stored)


def _hash_limited(password: str) -> str:
    with _HASH_SLOTS:
        return hash_password(password)


async def verify_password_async(password: str, stored: str) -> bool:
    return await run_in_threadpool(_verify_limited, password, stored)


async def hash_password_async(password: str) -> str:
    return await run_in_threadpool(_hash_limited, password)
