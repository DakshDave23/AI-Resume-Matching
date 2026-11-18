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
.PHONY: help db-up db-down db-reset db-logs db-shell migrate seed samples install dev test lint format typecheck check

help:  ## List targets
	@$(LIST_TARGETS)

# --- Database ---------------------------------------------------------------
db-up:  ## Start Postgres + pgvector and wait until it is healthy
	$(COMPOSE) up -d --wait db

db-down:  ## Stop Postgres (keeps data)
	$(COMPOSE) down

db-reset:  ## Stop Postgres and DELETE all data, then start fresh
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

# --- Backend ----------------------------------------------------------------
install:  ## Create the backend venv and install dependencies
	cd backend && $(PYTHON) -m venv .venv && $(VENV_PY) -m pip install -e ".[dev]"

dev:  ## Run the API with auto-reload on http://localhost:8000
	cd backend && $(UVICORN) app.main:app --reload

test:  ## Run backend tests
	cd backend && $(PYTEST)

lint:  ## Lint and check formatting
	cd backend && $(RUFF) check . && $(RUFF) format --check .

format:  ## Auto-fix lint issues and format
	cd backend && $(RUFF) check --fix . && $(RUFF) format .

typecheck:  ## Run mypy
	cd backend && $(MYPY) app tests

check: lint typecheck test  ## Everything CI runs
