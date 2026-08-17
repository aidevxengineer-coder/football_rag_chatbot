import hashlib
import secrets
from datetime import datetime, timezone

import bcrypt
import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from futbot_common.errors import AuthError, TokenError
from futbot_common.jwt_tokens import create_token, decode_token
from services.auth.config import settings
from services.auth.models import RecoveryCode, RefreshToken, User

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encrypt_totp_secret(secret: str) -> str:
    # ponytail: XOR-less dev encoding; replace with Fernet if compliance requires
    return hashlib.sha256((settings.jwt_secret + secret).encode()).hexdigest()[:32] + ":" + secret


def decrypt_totp_secret(encrypted: str) -> str:
    return encrypted.split(":", 1)[1]


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(4) for _ in range(count)]


async def create_user(
    session: AsyncSession, email: str, password: str, first_name: str
) -> User:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        raise AuthError("EMAIL_EXISTS", "Email already registered", 409)
    user = User(
        email=email.lower(),
        first_name=first_name.strip(),
        password_hash=hash_password(password),
        status="pending_verification",
        totp_enabled=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def create_setup_token(user_id: str) -> str:
    return create_token(
        user_id, settings.jwt_secret, "setup", settings.setup_delta()
    )


def create_step_up_token(user_id: str) -> str:
    return create_token(
        user_id, settings.jwt_secret, "step_up", settings.step_up_delta()
    )


def create_access_token(user: User) -> str:
    return create_token(
        user.id,
        settings.jwt_secret,
        "access",
        settings.access_delta(),
        extra_claims={"email": user.email, "first_name": user.first_name},
    )


async def create_refresh_token(session: AsyncSession, user_id: str) -> str:
    raw = create_token(
        user_id, settings.jwt_secret, "refresh", settings.refresh_delta()
    )
    payload = decode_token(raw, settings.jwt_secret, "refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return raw


async def issue_token_pair(session: AsyncSession, user: User) -> dict[str, str | int]:
    access = create_access_token(user)
    refresh = await create_refresh_token(session, user.id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.access_token_minutes * 60,
        "token_type": "bearer",
    }


async def enable_2fa(session: AsyncSession, user: User) -> dict[str, object]:
    if user.status != "active":
        raise AuthError("INVALID_STATE", "Account must be active", 400)
    if user.totp_enabled:
        raise AuthError("INVALID_STATE", "2FA already enabled", 400)
    secret = pyotp.random_base32()
    user.totp_secret_encrypted = encrypt_totp_secret(secret)
    codes = generate_recovery_codes()
    for code in codes:
        session.add(
            RecoveryCode(user_id=user.id, code_hash=hash_token(code))
        )
    await session.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name="FutBot"
    )
    return {"secret_uri": uri, "recovery_codes": codes}


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


async def activate_user(session: AsyncSession, user: User) -> User:
    user.status = "active"
    await session.commit()
    await session.refresh(user)
    return user


async def activate_user_after_2fa(session: AsyncSession, user: User) -> User:
    user.totp_enabled = True
    user.status = "active"
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_password(
    session: AsyncSession, email: str, password: str
) -> User:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if not user or not user.password_hash:
        raise AuthError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    if not verify_password(password, user.password_hash):
        raise AuthError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    if user.status == "pending_verification":
        raise AuthError(
            "VERIFY_REQUIRED",
            "Verify your email before signing in.",
            403,
        )
    if user.status != "active":
        raise AuthError("UNAUTHORIZED", "Account is not active.", 403)
    return user


async def verify_recovery_code(session: AsyncSession, user: User, code: str) -> bool:
    code_hash = hash_token(code.strip())
    stored = await session.scalar(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == code_hash,
            RecoveryCode.used_at.is_(None),
        )
    )
    if not stored:
        return False
    stored.used_at = datetime.now(timezone.utc)
    await session.commit()
    return True


def parse_bearer_token(authorization: str | None, expected_type: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("UNAUTHORIZED", "Missing bearer token", 401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return decode_token(token, settings.jwt_secret, expected_type)
    except TokenError as exc:
        raise AuthError("UNAUTHORIZED", "Invalid token", 401) from exc
