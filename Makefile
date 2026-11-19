# Developer shortcuts. Each target is a thin wrapper; the README lists the
# plain commands for shells without `make`.
#
# On Windows, GNU make runs recipes with cmd.exe, which needs backslash paths
# and has no grep/awk, so tool paths and `help` are chosen per OS.

ifeq ($(OS),Windows_NT)
  PYTHON  := py -3.12
  VENV    := .venv\Scripts
  VENV_PY := $(VENV)\python
  UVICORN := $(VENV)\uvicorn
  PYTEST  := $(VENV)\pytest
  RUFF    := $(VENV)\ruff
  MYPY    := $(VENV)\mypy
  ALEMBIC := $(VENV)\alembic
  BACKEND_PY := backend\.venv\Scripts\python
  LIST_TARGETS := findstr /R /C:"^[a-z-]*:.*\#\# " Makefile
else
  PYTHON  := python3.12
  VENV    := .venv/bin
  VENV_PY := $(VENV)/python
  UVICORN := $(VENV)/uvicorn
  PYTEST  := $(VENV)/pytest
  RUFF    := $(VENV)/ruff
  MYPY    := $(VENV)/mypy
  ALEMBIC := $(VENV)/alembic
  BACKEND_PY := backend/.venv/bin/python
  LIST_TARGETS := grep -E '^[a-z-]+:.*\#\# ' Makefile | awk 'BEGIN {FS = ":.*\#\# "}; {printf "  %-10s %s\n", $$1, $$2}'
endif

COMPOSE := docker compose
DB_USER ?= resume
DB_NAME ?= resume_matcher

.DEFAULT_GOAL := help
.PHONY: help up down logs db-up db-down db-reset db-logs db-shell migrate seed samples eval-parsing eval-ranking install dev test lint format typecheck check web-install web web-check types

help:  ## List targets
	@$(LIST_TARGETS)

# --- Everything in Docker -------------------------------------------------------
up:  ## Build and start db, backend and web; the app is on http://localhost:8080
	$(COMPOSE) up --build -d --wait

down:  ## Stop every container (keeps data and uploads)
	$(COMPOSE) down

logs:  ## Follow the logs of every container
	$(COMPOSE) logs -f

# --- Database ---------------------------------------------------------------
db-up:  ## Start Postgres + pgvector and wait until it is healthy
	$(COMPOSE) up -d --wait db

db-down:  ## Stop Postgres (keeps data)
	$(COMPOSE) stop db

db-reset:  ## Stop everything, DELETE all data and uploads, then start a fresh Postgres
	$(COMPOSE) down -v
	$(COMPOSE) up -d --wait db

db-logs:  ## Follow Postgres logs
	$(COMPOSE) logs -f db

db-shell:  ## Open psql inside the database container
	$(COMPOSE) exec db psql -U $(DB_USER) -d $(DB_NAME)

migrate:  ## Apply all database migrations
	cd backend && $(ALEMBIC) upgrade head

seed:  ## Load the skills taxonomy into the database (safe to re-run)
	$(BACKEND_PY) scripts/seed_skills.py

samples:  ## Regenerate sample resumes and ground_truth.json from the personas
	$(BACKEND_PY) scripts/generate_samples.py

eval-parsing:  ## Measure parsing accuracy on the samples; saves docs/parsing-accuracy.md
	$(BACKEND_PY) scripts/evaluate_parsing.py --out docs/parsing-accuracy.md

eval-ranking:  ## Measure ranking quality on the samples; saves docs/ranking-results.md
	$(BACKEND_PY) scripts/evaluate_ranking.py --out docs/ranking-results.md

# --- Backend ----------------------------------------------------------------
install:  ## Create the backend venv and install dependencies
	cd backend && $(PYTHON) -m venv .venv && $(VENV_PY) -m pip install -e ".[dev]"

dev:  ## Run the API with auto-reload on http://localhost:8000
	cd backend && $(UVICORN) app.main:app --reload

test:  ## Run backend tests
	cd backend && $(PYTEST)

lint:  ## Lint and check formatting (backend and scripts)
	cd backend && $(RUFF) check . ../scripts && $(RUFF) format --check . ../scripts

format:  ## Auto-fix lint issues and format
	cd backend && $(RUFF) check --fix . ../scripts && $(RUFF) format . ../scripts

typecheck:  ## Run mypy
	cd backend && $(MYPY) app tests ../scripts

check: lint typecheck test  ## Everything CI runs

# --- Frontend ---------------------------------------------------------------
web-install:  ## Install the frontend's exact dependencies (npm ci)
	cd frontend && npm ci

web:  ## Run the frontend with hot reload on http://localhost:5173
	cd frontend && npm run dev

web-check:  ## Lint, format-check, type-check, test and build the frontend
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build

types:  ## Regenerate frontend/src/types/api.ts from the API's OpenAPI schema
	$(BACKEND_PY) scripts/export_openapi.py && cd frontend && npm run generate:types
