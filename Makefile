.DEFAULT_GOAL := help
.PHONY: help sync run web lint format typecheck test up down logs build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## Install/resolve dependencies (incl. local akgentic-tool & akgentic-llm)
	uv sync

run: ## Run the backend API locally (reload)
	uv run uvicorn knowledge_akgents.app:app --reload --host 0.0.0.0 --port 8000

web: ## Serve the static frontend locally on :8080 (use ?backend=localhost:8000)
	uv run python -m http.server 8080 --directory frontend

lint: ## Lint with ruff
	uv run ruff check .

format: ## Format with ruff
	uv run ruff format .

typecheck: ## Type-check the backend with mypy
	uv run mypy src

test: ## Run the test suite
	uv run pytest

build: ## Build the Docker images
	docker compose build

up: ## Start the full stack (qdrant + backend + web) in Docker
	docker compose up -d --build

down: ## Stop the stack
	docker compose down

logs: ## Tail backend logs
	docker compose logs -f backend

clean: ## Remove caches and the virtualenv
	rm -rf .venv .ruff_cache .mypy_cache .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
