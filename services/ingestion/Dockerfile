FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY packages/futbot-common packages/futbot-common
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ingestion services/ingestion
COPY services/retrieval/indexer.py services/retrieval/indexer.py
COPY services/retrieval/schemas.py services/retrieval/schemas.py
COPY services/retrieval/__init__.py services/retrieval/__init__.py
COPY scripts/seed_global_kb.py scripts/seed_global_kb.py
COPY services/llm_gateway services/llm_gateway
COPY services/__init__.py services/__init__.py

ENV PYTHONPATH=/app
CMD ["uvicorn", "services.ingestion.main:app", "--host", "0.0.0.0", "--port", "8086"]
