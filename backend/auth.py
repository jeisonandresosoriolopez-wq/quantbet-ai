"""Sistema de autenticación y protección con contraseña para QuantBet."""
from __future__ import annotations

import hashlib
import hmac
from . import config, db


def get_active_password() -> str:
    pwd = db.get_setting("app_password")
    if pwd and pwd.strip():
        return pwd.strip()
    return config.APP_PASSWORD


def generate_token(password: str) -> str:
    key = config.SECRET_SALT.encode("utf-8")
    msg = f"quantbet_auth:{password}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_password(password: str) -> bool:
    expected = get_active_password()
    return hmac.compare_digest(password.strip(), expected)


def verify_token(token: str) -> bool:
    if not token:
        return False
    expected_token = generate_token(get_active_password())
    return hmac.compare_digest(token.strip(), expected_token)


def set_new_password(new_password: str) -> str:
    clean = new_password.strip()
    db.set_setting("app_password", clean)
    return generate_token(clean)
