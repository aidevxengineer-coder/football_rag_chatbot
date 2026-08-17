"""Token budgeting helpers — shrink prompts without dropping whole facts."""

from __future__ import annotations

import json
from typing import Any

import tiktoken

_DEFAULT_ENCODING = "cl100k_base"
_enc = tiktoken.get_encoding(_DEFAULT_ENCODING)

TRUNCATION_MARKER = "\n[... content shortened to fit model limits ...]\n"


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc.encode(text))


def trim_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    tokens = _enc.encode(text or "")
    if len(tokens) <= max_tokens:
        return text
    return _enc.decode(tokens[:max_tokens])


def trim_preserve_edges(text: str, max_tokens: int) -> str:
    """Keep the start and end of *text* so facts at both ends survive trimming."""
    if max_tokens <= 0:
        return ""
    tokens = _enc.encode(text or "")
    if len(tokens) <= max_tokens:
        return text

    marker_tokens = _enc.encode(TRUNCATION_MARKER)
    remaining = max_tokens - len(marker_tokens)
    if remaining < 16:
        return _enc.decode(tokens[:max_tokens])

    head_len = remaining // 2
    tail_len = remaining - head_len
    return (
        _enc.decode(tokens[:head_len])
        + TRUNCATION_MARKER
        + _enc.decode(tokens[-tail_len:])
    )


def fit_messages_for_prompt(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
) -> str:
    """Render chat history newest-first within the token budget."""
    if not messages or max_tokens <= 0:
        return ""

    lines: list[str] = []
    used = 0
    for message in reversed(messages):
        line = f"{message.get('role', 'user')}: {message.get('content', '')}"
        line_tokens = count_tokens(line)
        if used + line_tokens <= max_tokens:
            lines.append(line)
            used += line_tokens
            continue

        remaining = max_tokens - used
        if remaining < 32:
            break
        trimmed = trim_preserve_edges(line, remaining)
        lines.append(trimmed)
        break

    lines.reverse()
    return "\n".join(lines)


def _compact_tool_payload(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return str(payload)


def build_context_text_within_budget(
    chunks: list[dict[str, Any]],
    tool_results: list[dict[str, Any]] | None = None,
    *,
    max_tokens: int,
) -> str:
    """Build retrieval context, allocating tokens by relevance instead of dropping chunks."""
    if max_tokens <= 0:
        return "(no context provided)"

    segments: list[tuple[float, str, str]] = []

    for tr in tool_results or []:
        payload = tr.get("result") if isinstance(tr.get("result"), dict) else tr
        label = f"[TOOL: {tr.get('tool', 'unknown')}]"
        body = _compact_tool_payload(payload)
        segments.append((5.0, label, body))

    for index, chunk in enumerate(chunks):
        score = float(chunk.get("rrf_score") or 0.0)
        if score <= 0:
            score = 1.0 / (index + 1)
        label = f"Source [{chunk.get('chunk_id', 'unknown')}]:"
        body = str(chunk.get("document") or "")
        segments.append((score, label, body))

    if not segments:
        return "(no context provided)"

    label_tokens = sum(count_tokens(f"{label}\n") for _, label, _ in segments)
    body_budget = max(max_tokens - label_tokens, max_tokens // 2)
    weight_sum = sum(weight for weight, _, _ in segments) or 1.0

    parts: list[str] = []
    allocations: list[int] = []
    for weight, label, body in segments:
        allocation = max(96, int(body_budget * (weight / weight_sum)))
        allocations.append(allocation)
        trimmed_body = trim_preserve_edges(body, allocation)
        parts.append(f"{label}\n{trimmed_body}")

    combined = "\n\n".join(parts)
    while count_tokens(combined) > max_tokens and any(alloc > 48 for alloc in allocations):
        allocations = [max(48, int(alloc * 0.85)) for alloc in allocations]
        parts = []
        for (_, label, body), allocation in zip(segments, allocations):
            parts.append(f"{label}\n{trim_preserve_edges(body, allocation)}")
        combined = "\n\n".join(parts)

    return combined


def fit_llm_input(
    *,
    system_prompt: str,
    user_prompt: str,
    max_input_tokens: int,
) -> str:
    """Ensure system + user prompts fit within a model input budget."""
    reserved = count_tokens(system_prompt) + 64
    user_budget = max(max_input_tokens - reserved, 32)
    if count_tokens(user_prompt) <= user_budget:
        return user_prompt
    return trim_preserve_edges(user_prompt, user_budget)
