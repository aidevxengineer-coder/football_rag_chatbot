"""Authenticated self-hosted configuration endpoints."""

import errno
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator

from futbot_common.responses import DataResponse
from services.gateway.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED_API_KEYS = (
    "GROQ_API_KEY",
    "TAVILY_API_KEY",
    "SERPER_API_KEY",
    "API_FOOTBALL_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
)


class ApiKeysPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    GROQ_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None
    SERPER_API_KEY: str | None = None
    API_FOOTBALL_KEY: str | None = None
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    @field_validator("*")
    @classmethod
    def validate_env_value(cls, value: str | None) -> str | None:
        if value is not None and ("\n" in value or "\r" in value or "\x00" in value):
            raise ValueError("API key values must be single-line strings")
        return value


def _ensure_env_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    example = path.with_name(".env.example")
    if example.is_file():
        path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        path.touch()


def _parse_allowed_values(path: Path) -> dict[str, str]:
    _ensure_env_file(path)
    values = {key: "" for key in ALLOWED_API_KEYS}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            values[key] = value.strip()
    return values


def _write_values(path: Path, updates: dict[str, str]) -> None:
    _ensure_env_file(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    written: set[str] = set()
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                if key not in written:
                    output.append(f"{key}={updates[key]}")
                    written.add(key)
                continue
        output.append(raw_line)

    missing = [key for key in ALLOWED_API_KEYS if key in updates and key not in written]
    if missing:
        if output and output[-1] != "":
            output.append("")
        output.extend(f"{key}={updates[key]}" for key in missing)

    content = "\n".join(output)
    if content and not content.endswith("\n"):
        content += "\n"

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temp_name, path)
        except OSError as exc:
            # Docker bind-mounted files cannot be replaced as directory entries.
            # Fall back to an in-place write so the host .env still receives updates.
            if exc.errno not in {errno.EBUSY, errno.EACCES, errno.EPERM}:
                raise
            path.write_text(content, encoding="utf-8", newline="\n")
            os.unlink(temp_name)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


@router.get("/api-keys", response_model=DataResponse[dict[str, str]])
def get_api_keys() -> DataResponse[dict[str, str]]:
    return DataResponse(data=_parse_allowed_values(settings.env_file))


@router.put("/api-keys", response_model=DataResponse[dict[str, str]])
def put_api_keys(body: ApiKeysPayload) -> DataResponse[dict[str, str]]:
    updates = {
        key: value
        for key, value in body.model_dump(exclude_none=True).items()
        if key in ALLOWED_API_KEYS
    }
    _write_values(settings.env_file, updates)
    return DataResponse(data=_parse_allowed_values(settings.env_file))
