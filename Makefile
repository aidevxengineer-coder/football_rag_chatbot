# FutBot development Makefile
#
#   make install   - install deps + bootstrap prerequisites
#   make backend   - run API gateway on :8000
#   make frontend  - run Pitchside Next.js on :3000

PYTHON ?= python
NPM    ?= npm
API_PORT ?= 8000
WEB_PORT ?= 3000

export PYTHONPATH := .

.PHONY: help install backend frontend seed-kb

RETRIEVAL_URL ?= http://localhost:8085
GLOBAL_KB_CSV ?= final-articles.csv

help:
	@echo "FutBot Makefile targets:"
	@echo "  make install   Install Python dependencies and bootstrap prerequisites"
	@echo "  make backend   Run API gateway at http://localhost:$(API_PORT)"
	@echo "  make frontend  Run Pitchside web at http://localhost:$(WEB_PORT)"
	@echo "  make seed-kb   Index final-articles.csv into global knowledge base"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON) NPM=$(NPM) API_PORT=$(API_PORT) WEB_PORT=$(WEB_PORT)"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -c "import nltk; [nltk.download(r, quiet=True) for r in ('punkt', 'punkt_tab')]"
	$(PYTHON) -c "import os; os.makedirs('data', exist_ok=True)"
	@$(PYTHON) -c "import os; print('Note: create a .env file with API keys (see README).') if not os.path.exists('.env') else print('.env found')"
	@echo "Optional: install Tesseract OCR for image text extraction (e.g. choco install tesseract on Windows)"

backend: install-check
	$(PYTHON) -m uvicorn services.gateway.main:app --host 0.0.0.0 --port $(API_PORT) --reload --reload-dir services/gateway

frontend:
	$(NPM) --prefix services/web run dev -- --port $(WEB_PORT)

# Lightweight guard so backend/frontend fail fast with a helpful message
install-check:
	@$(PYTHON) -c "import uvicorn" || (echo "Dependencies missing. Run: make install" && exit 1)

seed-kb: install-check
	RETRIEVAL_SERVICE_URL=$(RETRIEVAL_URL) $(PYTHON) scripts/seed_global_kb.py --csv $(GLOBAL_KB_CSV)
