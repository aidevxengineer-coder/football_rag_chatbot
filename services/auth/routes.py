from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from futbot_common.errors import AuthError, TokenError
from futbot_common.jwt_tokens import decode_token
from futbot_common.responses import DataResponse
from services.auth.config import settings
from services.auth.db import get_db
from services.auth.email_verification import (
    check_verification_code,
    dev_verification_code_for_register,
    issue_verification_code,
)
from services.auth.models import OAuthAccount, RefreshToken, User
from services.auth.redis_store import blocklist_jti, is_jti_blocklisted
from services.auth.schemas import (
    Enable2FAResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    Verify2FARequest,
    VerifyEmailRequest,
    OAuthProvidersResponse,
)
from services.auth.security import (
    activate_user,
    activate_user_after_2fa,
    authenticate_password,
    create_setup_token,
    create_step_up_token,
    enable_2fa,
    hash_token,
    issue_token_pair,
    parse_bearer_token,
    create_user,
    verify_recovery_code,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()


def _configure_oauth() -> None:
    if settings.google_client_id and settings.google_client_secret:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


_configure_oauth()


@router.post("/register", response_model=DataResponse[RegisterResponse], status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, body.email, body.password, body.first_name)
    verification_token = create_setup_token(user.id)
    code, email_sent, email_error = await issue_verification_code(user.id, user.email)
    return DataResponse(
        data=RegisterResponse(
            user_id=user.id,
            email=user.email,
            first_name=user.first_name,
            status=user.status,
            verification_token=verification_token,
            verification_email_sent=email_sent,
            dev_verification_code=dev_verification_code_for_register(code, email_sent),
            verification_email_error=email_error if not email_sent else None,
        )
    )


@router.post("/verify-email", response_model=DataResponse[TokenResponse])
async def verify_email(
    body: VerifyEmailRequest,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    payload = parse_bearer_token(authorization, "setup")
    user = await db.get(User, payload["sub"])
    if not user:
        raise AuthError("UNAUTHORIZED", "User not found", 401)
    if user.status != "pending_verification":
        raise AuthError("INVALID_STATE", "Email verification not required", 400)
    if not await check_verification_code(user.id, body.code):
        raise AuthError("INVALID_CODE", "Invalid or expired verification code", 401)
    await activate_user(db, user)
    tokens = await issue_token_pair(db, user)
    return DataResponse(data=TokenResponse(**tokens))


@router.post("/login", response_model=DataResponse[LoginResponse])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_password(db, body.email, body.password)
    if user.totp_enabled:
        step_up_token = create_step_up_token(user.id)
        return DataResponse(data=LoginResponse(requires_2fa=True, step_up_token=step_up_token))
    tokens = await issue_token_pair(db, user)
    return DataResponse(data=LoginResponse(**tokens))


@router.post("/2fa/enable", response_model=DataResponse[Enable2FAResponse])
async def setup_2fa(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    # Accept a fresh registration "setup" token, or an "access" token from
    # any already-logged-in user opting into 2FA from Settings.
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    payload = None
    for expected in ("setup", "access"):
        try:
            payload = decode_token(token, settings.jwt_secret, expected)
            break
        except Exception:
            continue
    if not payload:
        raise AuthError("UNAUTHORIZED", "Missing or invalid bearer token", 401)

    user = await db.get(User, payload["sub"])
    if not user:
        raise AuthError("UNAUTHORIZED", "User not found", 401)
    if user.status != "active":
        raise AuthError("INVALID_STATE", "Account must be active", 400)
    if user.totp_enabled:
        raise AuthError("INVALID_STATE", "2FA already enabled", 400)
    result = await enable_2fa(db, user)
    return DataResponse(data=Enable2FAResponse(**result))


@router.post("/2fa/verify", response_model=DataResponse[TokenResponse])
async def verify_2fa(
    body: Verify2FARequest,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    user_id = None
    is_confirming_setup = False
    for expected in ("setup", "access", "step_up"):
        try:
            payload = decode_token(token, settings.jwt_secret, expected)
            user_id = payload["sub"]
            # "setup" (post-registration) and "access" (opt-in from Settings)
            # both mean: confirm the pending TOTP enrollment. "step_up" means
            # a normal login is being completed with an existing 2FA device.
            is_confirming_setup = expected in ("setup", "access")
            break
        except Exception:
            continue
    if not user_id:
        raise AuthError("UNAUTHORIZED", "Invalid token", 401)

    user = await db.get(User, user_id)
    if not user:
        raise AuthError("INVALID_CODE", "Invalid 2FA code", 401)
    if not verify_totp(user, body.code) and not await verify_recovery_code(db, user, body.code):
        raise AuthError("INVALID_CODE", "Invalid 2FA code", 401)

    if is_confirming_setup:
        await activate_user_after_2fa(db, user)
    tokens = await issue_token_pair(db, user)
    return DataResponse(data=TokenResponse(**tokens))


@router.post("/refresh", response_model=DataResponse[TokenResponse])
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, settings.jwt_secret, "refresh")
    except TokenError as exc:
        raise AuthError("INVALID_TOKEN", "Invalid refresh token", 401) from exc
    stored = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(body.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise AuthError("INVALID_TOKEN", "Invalid refresh token", 401)
    stored.revoked_at = datetime.now(timezone.utc)
    user = await db.get(User, payload["sub"])
    if not user or user.status != "active":
        raise AuthError("UNAUTHORIZED", "User not active", 401)
    tokens = await issue_token_pair(db, user)
    await db.commit()
    return DataResponse(data=TokenResponse(**tokens))


@router.post("/logout", status_code=204)
async def logout(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    payload = parse_bearer_token(authorization, "access")
    if await is_jti_blocklisted(payload["jti"]):
        return None
    exp = int(payload["exp"])
    ttl = max(exp - int(datetime.now(timezone.utc).timestamp()), 1)
    await blocklist_jti(payload["jti"], ttl)
    return None


@router.get("/me", response_model=DataResponse[UserResponse])
async def me(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    payload = parse_bearer_token(authorization, "access")
    if await is_jti_blocklisted(payload["jti"]):
        raise AuthError("UNAUTHORIZED", "Token revoked", 401)
    user = await db.get(User, payload["sub"])
    if not user:
        raise AuthError("UNAUTHORIZED", "User not found", 401)
    return DataResponse(
        data=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            status=user.status,
            totp_enabled=user.totp_enabled,
        )
    )


@router.get("/oauth/providers", response_model=DataResponse[OAuthProvidersResponse])
async def oauth_providers() -> DataResponse[OAuthProvidersResponse]:
    return DataResponse(
        data=OAuthProvidersResponse(google="google" in oauth._clients)
    )


@router.get("/oauth/google")
async def google_login(request: Request):
    if "google" not in oauth._clients:
        raise AuthError("OAUTH_UNAVAILABLE", "Google OAuth not configured", 501)
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/oauth/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if "google" not in oauth._clients:
        raise AuthError("OAUTH_UNAVAILABLE", "Google OAuth not configured", 501)
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    if not email:
        raise AuthError("OAUTH_FAILED", "Google account missing email", 400)
    first_name = userinfo.get("given_name") or userinfo.get("name") or "User"
    provider_user_id = userinfo["sub"]

    oauth_account = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )
    if oauth_account:
        user = await db.get(User, oauth_account.user_id)
    else:
        user = await db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            user = User(
                email=email.lower(),
                first_name=first_name,
                password_hash=None,
                status="active",
                totp_enabled=False,
            )
            db.add(user)
            await db.flush()
        elif user.first_name in {"", "User"} and first_name:
            user.first_name = first_name
        db.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_user_id=provider_user_id,
            )
        )
        await db.commit()
        await db.refresh(user)

    tokens = await issue_token_pair(db, user)
    query = urlencode(
        {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_in": str(tokens["expires_in"]),
        }
    )
    return RedirectResponse(f"{settings.web_app_url.rstrip('/')}/auth/callback?{query}")
