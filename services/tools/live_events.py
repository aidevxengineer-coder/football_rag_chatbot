"""Normalize supported football MCP responses into a stable UI contract."""

import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from services.tools.registry import execute_tool, list_tools
from services.tools.schemas import LiveEvent, LiveEventsResponse

LIVE_TOOL_CANDIDATES = (
    ("mcp:livescore:get_live_scores", "LiveScore MCP"),
    ("mcp:api-football:get_live_matches", "API-Football"),
)
LIVE_EVENTS_CACHE_SECONDS = 30.0
_cache_lock = threading.Lock()
_cache_key: tuple[str, ...] | None = None
_cache_expires_at = 0.0
_cache_value: LiveEventsResponse | None = None


def _dig(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first(value: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        found = _dig(value, *path)
        if found is not None and found != "":
            return found
    return None


def _name(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        raw = value.get("name") or value.get("shortName") or value.get("short_name")
        return str(raw).strip() if raw else None
    return None


def _score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _event_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if not isinstance(raw, dict):
        return []

    paths = (
        ("events",),
        ("matches",),
        ("fixtures",),
        ("live",),
        ("data",),
        ("result",),
        ("response", "live"),
        ("response",),
    )
    for path in paths:
        rows = _dig(raw, *path)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            nested = _event_rows(rows)
            if nested:
                return nested

    if any(key in raw for key in ("teams", "home", "homeTeam", "home_team")):
        return [raw]
    return []


def normalize_live_events(raw: Any) -> list[LiveEvent]:
    events: list[LiveEvent] = []
    for index, row in enumerate(_event_rows(raw)):
        home = _name(
            _first(
                row,
                (
                    ("teams", "home"),
                    ("home",),
                    ("homeTeam",),
                    ("home_team",),
                ),
            )
        )
        away = _name(
            _first(
                row,
                (
                    ("teams", "away"),
                    ("away",),
                    ("awayTeam",),
                    ("away_team",),
                ),
            )
        )
        if not home or not away:
            continue

        home_score = _score(
            _first(
                row,
                (
                    ("goals", "home"),
                    ("score", "home"),
                    ("scores", "home"),
                    ("homeScore",),
                    ("home_score",),
                ),
            )
        )
        away_score = _score(
            _first(
                row,
                (
                    ("goals", "away"),
                    ("score", "away"),
                    ("scores", "away"),
                    ("awayScore",),
                    ("away_score",),
                ),
            )
        )
        score_text = _first(
            row,
            (
                ("status", "scoreStr"),
                ("scoreStr",),
                ("score",),
            ),
        )
        if isinstance(score_text, str) and (home_score is None or away_score is None):
            match = re.search(r"(\d+)\s*[-:]\s*(\d+)", score_text)
            if match:
                home_score = int(match.group(1))
                away_score = int(match.group(2))

        status_raw = _first(
            row,
            (
                ("fixture", "status", "long"),
                ("fixture", "status", "short"),
                ("status", "long"),
                ("status", "name"),
                ("status", "short"),
                ("status",),
                ("state",),
            ),
        )
        status = str(status_raw) if not isinstance(status_raw, dict) and status_raw else "Live"
        minute_raw = _first(
            row,
            (
                ("fixture", "status", "elapsed"),
                ("status", "elapsed"),
                ("status", "liveTime", "short"),
                ("minute",),
                ("time",),
            ),
        )
        minute = str(minute_raw) if minute_raw is not None else None
        if minute and minute.isdigit():
            minute = f"{minute}'"

        competition = _name(
            _first(
                row,
                (
                    ("league",),
                    ("competition",),
                    ("tournament",),
                ),
            )
        ) or "Football"
        event_id = _first(
            row,
            (
                ("fixture", "id"),
                ("id",),
                ("match_id",),
                ("event_id",),
            ),
        )
        started_at = _first(
            row,
            (
                ("fixture", "date"),
                ("start_time",),
                ("started_at",),
                ("date",),
            ),
        )

        events.append(
            LiveEvent(
                id=str(event_id or f"{home}-{away}-{index}"),
                competition=competition,
                home_team=home,
                away_team=away,
                home_score=home_score,
                away_score=away_score,
                status=status,
                minute=minute,
                started_at=str(started_at) if started_at else None,
            )
        )
    return events


def _fetch_live_events_uncached(available: set[str]) -> LiveEventsResponse:
    failures: list[str] = []

    for tool_name, provider in LIVE_TOOL_CANDIDATES:
        if tool_name not in available:
            continue
        result = execute_tool(tool_name, {})
        if not result.success:
            failures.append(result.error_message or f"{provider} unavailable")
            continue
        events = normalize_live_events(result.result)
        return LiveEventsResponse(
            events=events,
            provider=provider,
            updated_at=datetime.now(timezone.utc),
            message=None if events else "No matches are live right now.",
        )

    message = (
        "Live-score providers are temporarily unavailable."
        if failures
        else "No live-score provider is configured."
    )
    return LiveEventsResponse(
        events=[],
        provider=None,
        updated_at=datetime.now(timezone.utc),
        message=message,
    )


def fetch_live_events() -> LiveEventsResponse:
    """Fetch live matches with a short cache to protect public MCP providers."""
    global _cache_key, _cache_expires_at, _cache_value

    available = {tool.name for tool in list_tools(include_web_search=False)}
    key = tuple(sorted(available))
    now = time.monotonic()
    with _cache_lock:
        if _cache_key == key and _cache_value is not None and now < _cache_expires_at:
            return _cache_value

        value = _fetch_live_events_uncached(available)
        _cache_key = key
        _cache_value = value
        _cache_expires_at = time.monotonic() + LIVE_EVENTS_CACHE_SECONDS
        return value
