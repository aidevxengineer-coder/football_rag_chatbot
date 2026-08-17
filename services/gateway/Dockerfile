FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY packages/futbot-common packages/futbot-common
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway services/gateway
COPY services/__init__.py services/__init__.py

ENV PYTHONPATH=/app
CMD ["uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
