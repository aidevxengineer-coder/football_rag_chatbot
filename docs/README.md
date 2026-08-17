# Pitchside ⚽

Pitchside is an advanced AI Football Analyst powered by a multi-LLM Retrieval-Augmented Generation (RAG) pipeline. It analyzes the latest football news from major sources to provide accurate, up-to-date answers about the football world, significantly reducing hallucinations.

## Features
- **Live News Retrieval**: Syncs the latest football news for up-to-date insights.
- **Multi-LLM Pipeline**: Uses an orchestrator, generator, and judge LLM to ensure accurate responses.
- **Hallucination Resistant**: Grounded in real articles.
- **Responsive Web UI**: A beautiful frontend to interact with the bot.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (if running locally without Docker)
- API keys (defined in `.env`)

### Installation & Execution
1. Clone the repository:
   ```bash
   git clone https://github.com/SabihAli/Pitchside.git
   cd Pitchside
   ```

2. Setup environment variables:
   ```bash
   cp .env.example .env
   ```
   Add the provider keys you use.

3. Run with Docker Compose:
   ```bash
   docker compose up --build
   ```

4. Access the App:
   - Pitchside web: `http://localhost:3000`
   - API gateway: `http://localhost:8000`
   - API Docs: `http://localhost:8000/docs`

## Architecture
- **Frontend**: Next.js App Router service in `services/web`.
- **Backend**: FastAPI microservices behind the API gateway.
- **Retrieval**: Qdrant dense search plus BM25 sparse retrieval.

## Development
See `PROJECT_PLAN.md`, `football_rag_prd.md`, and [`UI_REQUIREMENTS.md`](UI_REQUIREMENTS.md) (living UI spec for Phase 8) for detailed development guidelines and architecture.
