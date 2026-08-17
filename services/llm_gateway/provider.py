import json
import logging
import random
import re
import time as _time
from collections.abc import AsyncGenerator
from typing import Any

import requests
from prometheus_client import Counter, Histogram

from services.llm_gateway.config import settings
from services.llm_gateway.prompt_loader import get_prompt_parts
from services.llm_gateway.token_budget import fit_llm_input, trim_preserve_edges, count_tokens

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Domain metrics: how many LLM calls, of what outcome, and how long they
# take, broken down by provider/model/pipeline-step ("role", e.g.
# "drafter", "judge", "rewriter"). Scraped via the futbot_common
# setup_metrics() /metrics endpoint already registered on this service's
# FastAPI app -- these share the same default Prometheus registry.
LLM_CALLS_TOTAL = Counter(
    "futbot_llm_calls_total",
    "Total LLM calls made, by provider/model/step/outcome.",
    ["provider", "model", "step", "status"],
)
LLM_CALL_DURATION_SECONDS = Histogram(
    "futbot_llm_call_duration_seconds",
    "LLM call latency in seconds, by provider/model/step.",
    ["provider", "model", "step"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 80),
)

GROQ_MODEL_MAP: dict[str, str] = {
    "orchestrator": settings.groq_model_orchestrator,
    "classifier": settings.groq_model_orchestrator,
    "compressor": settings.groq_model_120b,
    "rewriter": settings.groq_model_32b,
    "tool_planner": settings.groq_model_main,
    "vision": settings.groq_model_main,
    "drafter": settings.groq_model_120b,
    "simple_responder": settings.groq_model_32b,
    "judge": settings.groq_model_main,
}

GROQ_THINKING_ROLES = {"judge"}

MODEL_ORCHESTRATOR = settings.model_orchestrator
MODEL_GENERATOR = settings.model_generator
MODEL_DECISION = settings.model_decision


def _strip_think_tags(text: str) -> str:
    stripped = re.sub(
        r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE
    )
    return stripped.strip()


def _shrink_groq_user_content(content: str | list[dict[str, Any]], target_tokens: int) -> str | list[dict[str, Any]]:
    if isinstance(content, list):
        text_part = next(
            (
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ),
            "",
        )
        shrunk = trim_preserve_edges(text_part, target_tokens)
        return [
            {**part, "text": shrunk}
            if isinstance(part, dict) and part.get("type") == "text"
            else part
            for part in content
        ]
    return trim_preserve_edges(str(content), target_tokens)


def _call_groq(
    role: str,
    system_prompt: str,
    user_content: str,
    image: bytes | None = None,
) -> tuple[str, str, int | None, int]:
    if not settings.groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment when using LLM_PROVIDER=groq."
        )

    model = GROQ_MODEL_MAP.get(role, settings.groq_model_main)
    thinking = role in GROQ_THINKING_ROLES

    fitted_user = fit_llm_input(
        system_prompt=system_prompt,
        user_prompt=user_content,
        max_input_tokens=settings.llm_max_input_tokens,
    )

    if image is not None:
        import base64

        img_b64 = base64.b64encode(image).decode("utf-8")
        user_msg_content = [
            {"type": "text", "text": fitted_user},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]
    else:
        user_msg_content = fitted_user

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg_content},
    ]

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if not thinking:
        model_lower = model.lower()
        if "gpt-oss" in model_lower or "gpt_oss" in model_lower:
            payload["reasoning_effort"] = "low"
        elif "qwen" in model_lower:
            payload["reasoning_effort"] = "none"

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    raw = ""
    clean = ""
    status_code: int | None = None
    t0 = _time.monotonic()
    shrink_attempts = 0
    user_token_budget = max(
        512,
        settings.llm_max_input_tokens - count_tokens(system_prompt) - 128,
    )

    for attempt in range(settings.groq_max_retries):
        try:
            resp = requests.post(
                GROQ_API_URL, json=payload, headers=headers, timeout=120
            )
            status_code = resp.status_code

            if resp.status_code == 413:
                shrink_attempts += 1
                current_user = payload["messages"][1]["content"]
                target = max(256, user_token_budget // (2**shrink_attempts))
                payload["messages"][1]["content"] = _shrink_groq_user_content(
                    current_user,
                    target,
                )
                logger.warning(
                    "Groq 413 on %s; shrinking user prompt to ~%s tokens (attempt %s).",
                    role,
                    target,
                    shrink_attempts,
                )
                if shrink_attempts >= 8:
                    latency_ms = int((_time.monotonic() - t0) * 1000)
                    return (
                        "",
                        (
                            "The model request was too large even after shrinking. "
                            "Try a shorter question or reduce retrieved context."
                        ),
                        status_code,
                        latency_ms,
                    )
                continue

            if resp.status_code == 429:
                retry_after = float(
                    resp.headers.get("retry-after", settings.groq_backoff_base**attempt)
                )
                wait = min(
                    retry_after + random.uniform(0, 0.5),
                    settings.groq_backoff_max_sec,
                )
                logger.warning(
                    "Groq 429 on attempt %s/%s. Waiting %.2fs.",
                    attempt + 1,
                    settings.groq_max_retries,
                    wait,
                )
                _time.sleep(wait)
                continue

            if resp.status_code in {502, 503, 504}:
                wait = min(
                    settings.groq_backoff_base**attempt + random.uniform(0, 0.5),
                    settings.groq_backoff_max_sec,
                )
                logger.warning(
                    "Groq %s on attempt %s/%s. Waiting %.2fs.",
                    resp.status_code,
                    attempt + 1,
                    settings.groq_max_retries,
                    wait,
                )
                _time.sleep(wait)
                continue

            resp.raise_for_status()
            raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            clean = _strip_think_tags(raw)
            latency_ms = int((_time.monotonic() - t0) * 1000)
            return raw, clean, status_code, latency_ms

        except requests.RequestException as e:
            logger.error("Groq API request error (attempt %s): %s", attempt + 1, e)
            if attempt == settings.groq_max_retries - 1:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                return raw, clean, status_code, latency_ms
            _time.sleep(
                min(
                    settings.groq_backoff_base**attempt + random.uniform(0, 0.5),
                    settings.groq_backoff_max_sec,
                )
            )

    latency_ms = int((_time.monotonic() - t0) * 1000)
    return raw, clean, status_code, latency_ms


def _local_endpoint(model_name: str) -> str:
    model_name_lower = model_name.lower()
    if "0.8b" in model_name_lower:
        return settings.url_08b
    if "2b" in model_name_lower:
        return settings.url_2b
    if "4b" in model_name_lower:
        return settings.url_4b
    return settings.url_2b


def _local_unconfigured_message(model_name: str) -> str:
    return (
        "The local LLM endpoint is not configured for this model. "
        f"Set URL_2B/URL_4B in Settings (or .env) for `{model_name}`, "
        "or switch LLM_PROVIDER to groq with a valid GROQ_API_KEY."
    )


def _call_local(model_name: str, prompt: str) -> tuple[str, str, str, int | None, int]:
    api_url = _local_endpoint(model_name)
    if not api_url:
        message = _local_unconfigured_message(model_name)
        return "", message, message, None, 0

    if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    else:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"think": False},
        }

    raw = ""
    clean = ""
    status_code: int | None = None
    t0 = _time.monotonic()

    try:
        resp = requests.post(api_url, json=payload, timeout=120)
        status_code = resp.status_code
        resp.raise_for_status()
        if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
            raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            raw = resp.json().get("response", "").strip()
        clean = _strip_think_tags(raw)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return api_url, raw, clean, status_code, latency_ms
    except requests.RequestException as e:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        logger.error("Error calling local LLM API (%s) at %s: %s", model_name, api_url, e)
        message = (
            f"I couldn't reach the local LLM at `{api_url}` "
            f"(HTTP {status_code or 'unknown'}). Check URL_2B/URL_4B and that the model server is running."
        )
        return api_url, message, message, status_code, latency_ms


def invoke_llm(
    prompt: str,
    model_name: str,
    step: str = "unknown",
    run_logger=None,
    iteration: int = 0,
    image: bytes | None = None,
    system_prompt: str | None = None,
) -> str:
    raw = ""
    clean = ""
    api_url = ""
    status_code: int | None = None
    latency_ms = 0

    if settings.llm_provider == "groq":
        api_url = GROQ_API_URL
        groq_model = GROQ_MODEL_MAP.get(step, settings.groq_model_main)
        sys_msg = system_prompt if system_prompt is not None else ""
        try:
            raw, clean, status_code, latency_ms = _call_groq(step, sys_msg, prompt, image=image)
        except ValueError as exc:
            clean = str(exc)
            raw = clean
            status_code = None
            latency_ms = 0
        log_model_name = groq_model
        if not clean.strip():
            clean = (
                "I couldn't generate a response — the Groq API returned an error "
                f"(HTTP {status_code or 'unknown'}). Verify GROQ_API_KEY and that "
                f"model `{groq_model}` is available on your Groq account."
            )
    else:
        local_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        api_url, raw, clean, status_code, latency_ms = _call_local(model_name, local_prompt)
        log_model_name = model_name

    call_status = "ok" if status_code is not None and 200 <= status_code < 300 else "error"
    LLM_CALLS_TOTAL.labels(
        provider=settings.llm_provider, model=log_model_name, step=step, status=call_status
    ).inc()
    LLM_CALL_DURATION_SECONDS.labels(
        provider=settings.llm_provider, model=log_model_name, step=step
    ).observe(latency_ms / 1000)

    if run_logger is not None:
        try:
            run_logger.log_llm_call(
                step=step,
                model_name=log_model_name,
                prompt=prompt,
                raw_response=raw,
                response=clean,
                api_url=api_url,
                status_code=status_code,
                latency_ms=latency_ms,
                iteration=iteration,
            )
        except Exception as log_err:
            logger.warning("Failed to log LLM call: %s", log_err)

    return clean


def invoke_llm_stream(
    prompt: str,
    model_name: str,
    step: str = "drafter",
    system_prompt: str | None = None,
) -> list[str]:
    """Non-streaming fallback tokens for local provider; Groq stream deferred to Phase 6 wiring."""
    text = invoke_llm(
        prompt,
        model_name=model_name,
        step=step,
        system_prompt=system_prompt,
    )
    return [text] if text else []


def parse_snapshot_json(raw: str, existing_snapshot: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, separators=(",", ":"))
    except json.JSONDecodeError:
        logger.warning("Snapshot compressor returned invalid JSON; keeping existing snapshot.")
        return existing_snapshot or "{}"
