.DEFAULT_GOAL := help
.PHONY: help sync upgrade run web eval-viewer lint format typecheck test test-evals eval-ingestion \
	eval-jettro eval-yuma eval-retrieval eval-variance eval-judge \
	eval-judge-stability up down logs build clean

EVAL_TIMEOUT ?= 180
EVAL_FLAGS ?=

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## Install/resolve dependencies (incl. local akgentic-tool & akgentic-llm)
	uv sync --all-groups

upgrade: ## Check for and install updates to all dependencies
	uv lock --upgrade
	uv sync

run: ## Run the backend API locally (reload)
	uv run uvicorn knowledge_akgents.app:app --reload --host 0.0.0.0 --port 8000

web: ## Serve the static frontend locally on :8080 (use ?backend=localhost:8000)
	uv run python -m http.server 8080 --directory frontend

eval-viewer: ## Serve the local evaluation report viewer on :8765
	uv run python -m http.server 8765 --bind 127.0.0.1 --directory eval-viewer

lint: ## Lint with ruff
	uv run ruff check .

format: ## Format with ruff
	uv run ruff format .

typecheck: ## Type-check the backend with mypy
	uv run mypy src

test: ## Run the test suite
	uv run pytest

test-evals: ## Run deterministic evaluation harness tests (no network/LLM)
	uv run pytest tests/test_eval_*.py tests/test_fixture_*.py tests/test_jettro_*.py \
		tests/test_yuma_*.py tests/test_live_*.py tests/test_retrieval_only_dataset.py \
		tests/test_observability_spike.py tests/test_judge_calibration.py

eval-ingestion: ## Run the paid fixed-fixture Jettro ingestion evaluation
	AKGENTIC_QDRANT_URL='' uv run python -m evals.observability_spike \
		--scenario ingestion --timeout $(EVAL_TIMEOUT) $(EVAL_FLAGS)

eval-jettro: ## Run the paid Jettro ingestion-and-query scenario
	AKGENTIC_QDRANT_URL='' uv run python -m evals.observability_spike \
		--scenario jettro-multi-turn --timeout $(EVAL_TIMEOUT) $(EVAL_FLAGS)

eval-yuma: ## Run the paid Yuma ingestion-and-query scenario
	AKGENTIC_QDRANT_URL='' uv run python -m evals.observability_spike \
		--scenario yuma-multi-turn --timeout $(EVAL_TIMEOUT) $(EVAL_FLAGS)

eval-retrieval: ## Run the paid retrieval and missing-knowledge cases once
	AKGENTIC_QDRANT_URL='' uv run python -m evals.observability_spike \
		--scenario retrieval-only --timeout $(EVAL_TIMEOUT) $(EVAL_FLAGS)

eval-variance: ## Run the paid retrieval variance sample (three repetitions)
	AKGENTIC_QDRANT_URL='' uv run python -m evals.observability_spike \
		--scenario retrieval-only --repeat 3 --timeout $(EVAL_TIMEOUT) $(EVAL_FLAGS)

eval-judge: ## Run the paid static LLM-judge calibration once
	uv run python -m evals.judge_calibration $(EVAL_FLAGS)

eval-judge-stability: ## Run the paid LLM-judge calibration three times
	uv run python -m evals.judge_calibration --repeat 3 $(EVAL_FLAGS)

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
