# JARVIS Makefile
.DEFAULT_GOAL := help
VENV := backend/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup install test run lint fmt docker-up docker-full docker-down clean health seed-ollama

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv + install backend deps + copy .env
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Setup complete. Edit .env, then 'make run'."

install: ## Install backend deps into existing venv
	$(PIP) install -r backend/requirements.txt

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest

run: ## Run the API (reload) on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate: ## Apply DB migrations (alembic upgrade head)
	cd backend && .venv/bin/python -m alembic upgrade head

migration: ## Create a new migration: make migration m="message"
	cd backend && .venv/bin/python -m alembic revision --autogenerate -m "$(m)"

lint: ## Lint with ruff (if installed)
	cd backend && .venv/bin/python -m ruff check . || echo "ruff not installed (pip install ruff)"

fmt: ## Format with ruff
	cd backend && .venv/bin/python -m ruff format . || echo "ruff not installed"

docker-up: ## Start minimal stack (backend only, SQLite)
	docker compose up -d backend

docker-full: ## Start full stack (postgres/redis/qdrant/ollama)
	docker compose --profile full up -d

docker-down: ## Stop all services
	docker compose --profile full --profile ui down

health: ## Curl the health endpoint
	curl -fsS http://localhost:8000/api/health | python3 -m json.tool

seed-ollama: ## Pull recommended local models via Ollama
	ollama pull llama3.1
	ollama pull qwen2.5-coder
	ollama pull mistral

clean: ## Remove caches and venv
	rm -rf $(VENV) backend/.pytest_cache backend/.ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
