import os
import re
from pathlib import Path

_PROMPTS_FILE = Path(
    os.getenv("PROMPTS_FILE", str(Path(__file__).resolve().parent / "prompts.txt"))
)
_prompts_cache: dict[str, str] = {}
_prompts_mtime: float | None = None


def load_prompts() -> dict[str, str]:
    global _prompts_cache, _prompts_mtime
    if not _PROMPTS_FILE.is_file():
        raise FileNotFoundError(f"Prompts file not found at {_PROMPTS_FILE}")
    mtime = _PROMPTS_FILE.stat().st_mtime
    if _prompts_cache and _prompts_mtime == mtime:
        return _prompts_cache

    content = _PROMPTS_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"^\[([A-Z_]+)\]\s*$", content, flags=re.MULTILINE)
    parsed: dict[str, str] = {}
    for i in range(1, len(blocks), 2):
        parsed[blocks[i]] = blocks[i + 1].strip()
    _prompts_cache = parsed
    _prompts_mtime = mtime
    return _prompts_cache


def get_prompt(name: str) -> str:
    prompts = load_prompts()
    if name not in prompts:
        raise KeyError(f"Prompt '{name}' not found in prompts.txt")
    return prompts[name]


def get_prompt_parts(name: str) -> tuple[str, str]:
    prompts = load_prompts()
    system_key = f"{name}_SYSTEM"
    user_key = f"{name}_USER"
    if system_key not in prompts:
        raise KeyError(f"System prompt '{system_key}' not found in prompts.txt")
    if user_key not in prompts:
        raise KeyError(f"User prompt '{user_key}' not found in prompts.txt")
    return prompts[system_key], prompts[user_key]


def clear_prompts_cache_for_tests() -> None:
    global _prompts_cache, _prompts_mtime
    _prompts_cache = {}
    _prompts_mtime = None
