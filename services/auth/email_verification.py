import asyncio
import logging
import secrets
import smtplib
from email.message import EmailMessage

from futbot_common.exception_handlers import is_dev_mode
from services.auth.config import settings
from services.auth.redis_store import get_redis
from services.auth.security import hash_token

logger = logging.getLogger(__name__)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_verification_code(user_id: str, email: str) -> tuple[str, bool, str | None]:
    code = _generate_code()
    redis = await get_redis()
    ttl = settings.verification_code_minutes * 60
    await redis.setex(f"auth:verify:{user_id}", ttl, hash_token(code))
    sent, error = await send_verification_email(email, code)
    return code, sent, error


def _send_smtp_email(*, to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    if settings.smtp_use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=30
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)

    with server as smtp:
        smtp.ehlo()
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def send_verification_email(email: str, code: str) -> tuple[bool, str | None]:
    subject = "Your Pitchside verification code"
    body = (
        f"Hi,\n\n"
        f"Your Pitchside verification code is: {code}\n\n"
        f"It expires in {settings.verification_code_minutes} minutes.\n\n"
        f"If you did not create an account, you can ignore this email."
    )

    if not settings.smtp_host:
        logger.warning(
            "SMTP_HOST is not configured; verification code for %s: %s",
            email,
            code,
        )
        return False, "SMTP_HOST is not configured"

    try:
        await asyncio.to_thread(
            _send_smtp_email,
            to_email=email,
            subject=subject,
            body=body,
        )
        logger.info("Sent verification email to %s", email)
        return True, None
    except Exception as exc:
        logger.exception("Failed to send verification email to %s", email)
        return False, str(exc)


def dev_verification_code_for_register(code: str, email_sent: bool) -> str | None:
    if email_sent or not is_dev_mode():
        return None
    return code


async def check_verification_code(user_id: str, code: str) -> bool:
    redis = await get_redis()
    stored = await redis.get(f"auth:verify:{user_id}")
    if not stored:
        return False
    normalized = code.strip().replace(" ", "")
    if stored != hash_token(normalized):
        return False
    await redis.delete(f"auth:verify:{user_id}")
    return True
