from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class Verify2FARequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    status: str
    verification_token: str
    verification_email_sent: bool = False
    dev_verification_code: str | None = None
    verification_email_error: str | None = None


class LoginResponse(BaseModel):
    requires_2fa: bool = False
    step_up_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None


class Enable2FAResponse(BaseModel):
    secret_uri: str
    recovery_codes: list[str]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    status: str
    totp_enabled: bool


class OAuthProvidersResponse(BaseModel):
    google: bool
