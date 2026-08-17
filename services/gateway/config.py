import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://localhost:8081")
        self.chat_service_url = os.getenv("CHAT_SERVICE_URL", "http://localhost:8082")
        self.project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://localhost:8083")
        self.llm_service_url = os.getenv("LLM_SERVICE_URL", "http://localhost:8087")
        self.retrieval_service_url = os.getenv("RETRIEVAL_SERVICE_URL", "http://localhost:8085")
        self.ingestion_service_url = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8086")
        self.orchestrator_service_url = os.getenv(
            "ORCHESTRATOR_SERVICE_URL", "http://localhost:8084"
        )
        self.observability_service_url = os.getenv(
            "OBSERVABILITY_SERVICE_URL", "http://localhost:8090"
        )
        self.tools_service_url = os.getenv("TOOLS_SERVICE_URL", "http://localhost:8088")
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.anon_message_limit = int(os.getenv("ANON_MESSAGE_LIMIT", "10"))
        repo_root = Path(__file__).resolve().parents[2]
        self.env_file = Path(os.getenv("ENV_FILE", str(repo_root / ".env")))


settings = Settings()
