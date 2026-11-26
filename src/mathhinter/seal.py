"""Seal a small JSON value so the page can carry it without reading or changing it: the similar exercise's answer
goes to the browser and back, and only the server can open it to check the student's reply.

HMAC-SHA256 in counter mode for the keystream, and HMAC-SHA256 over the ciphertext for integrity. It hides a practice
answer from casual view; it is not meant to protect anything valuable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os


class BadSeal(ValueError):
    pass


def _keys(secret: str) -> tuple[bytes, bytes]:
    root = hashlib.sha256(("math-hinter seal:" + secret).encode()).digest()
    return hmac.new(root, b"encrypt", hashlib.sha256).digest(), hmac.new(root, b"sign", hashlib.sha256).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = (hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(length // 32 + 1))
    return b"".join(blocks)[:length]


def seal(value: object, secret: str) -> str:
    encrypt, sign = _keys(secret)
    nonce = os.urandom(16)
    plain = json.dumps(value, ensure_ascii=False).encode()
    cipher = bytes(a ^ b for a, b in zip(plain, _stream(encrypt, nonce, len(plain)), strict=False))
    tag = hmac.new(sign, nonce + cipher, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode()


def unseal(token: str, secret: str) -> object:
    encrypt, sign = _keys(secret)
    try:
        raw = base64.urlsafe_b64decode(str(token).encode())
    except (ValueError, TypeError):
        raise BadSeal("not a token") from None
    nonce, tag, cipher = raw[:16], raw[16:32], raw[32:]
    if len(raw) < 33 or not hmac.compare_digest(tag, hmac.new(sign, nonce + cipher, hashlib.sha256).digest()[:16]):
        raise BadSeal("altered or foreign token")
    return json.loads(bytes(a ^ b for a, b in zip(cipher, _stream(encrypt, nonce, len(cipher)), strict=False)).decode())
