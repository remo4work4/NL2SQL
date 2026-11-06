"""密码哈希与 token 工具（纯 stdlib 实现，无第三方依赖）。"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

PBKDF2_ITERATIONS = 600_000


def utc_now() -> str:
    """UTC 时间字符串（微秒精度，可字典序比较，用于 DB 时间列）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hash_password(password: str) -> str:
    """PBKDF2-SHA256 哈希，格式: pbkdf2_sha256$iterations$salt_hex$hash_hex"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    """不透明会话 token（存 DB 校验，可撤销）。"""
    return secrets.token_urlsafe(32)
