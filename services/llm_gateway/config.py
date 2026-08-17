import os


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


class Settings:
    def __init__(self) -> None:
        self.llm_provider = _env("LLM_PROVIDER", "local").lower()
        self.groq_api_key = _env("GROQ_API_KEY")
        self.groq_max_retries = int(os.getenv("GROQ_MAX_RETRIES", "5"))
        self.groq_backoff_base = float(os.getenv("GROQ_BACKOFF_BASE", "1.5"))
        self.groq_backoff_max_sec = float(os.getenv("GROQ_BACKOFF_MAX_SEC", "60"))
        self.snapshot_max_tokens = int(os.getenv("SNAPSHOT_MAX_TOKENS", "300"))
        # Groq rejects oversized requests (HTTP 413). Keep prompts under safe limits.
        self.llm_max_input_tokens = int(os.getenv("LLM_MAX_INPUT_TOKENS", "12000"))
        self.llm_context_token_budget = int(
            os.getenv("LLM_CONTEXT_TOKEN_BUDGET", "6000")
        )
        self.llm_rewriter_context_budget = int(
            os.getenv("LLM_REWRITER_CONTEXT_BUDGET", "3000")
        )
        self.llm_judge_draft_token_budget = int(
            os.getenv("LLM_JUDGE_DRAFT_TOKEN_BUDGET", "1500")
        )
        self.llm_rate_limit_rpm = int(os.getenv("LLM_RATE_LIMIT_RPM", "60"))
        self.model_orchestrator = _env("MODEL_ORCHESTRATOR", "Qwen/Qwen3.5-0.8B")
        self.model_generator = _env("MODEL_GENERATOR", "Qwen/Qwen3.5-2B")
        self.model_decision = _env("MODEL_DECISION", "Qwen/Qwen3.5-4B")
        self.url_08b = _env("URL_08B")
        self.url_2b = _env("URL_2B")
        self.url_4b = _env("URL_4B")
        self.groq_model_120b = os.getenv("GROQ_MODEL_120B", "openai/gpt-oss-120b")
        # llama-3.1-8b-instant was retired by Groq (404s on all requests as of
        # 2026-08); openai/gpt-oss-20b is the smallest currently-live model.
        self.groq_model_32b = os.getenv("GROQ_MODEL_32B", "openai/gpt-oss-20b")
        self.groq_model_main = os.getenv("GROQ_MODEL_MAIN", "qwen/qwen3.6-27b")
        self.groq_model_orchestrator = os.getenv(
            "GROQ_MODEL_ORCHESTRATOR", "openai/gpt-oss-20b"
        )


settings = Settings()
