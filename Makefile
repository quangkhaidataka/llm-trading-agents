# Makefile — standardized commands. `make check` is the SINGLE source of truth
# for "is the code OK". All work happens in a project-local .venv so the system /
# conda env is never touched.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(PY) -m pip
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy
PYTEST  := $(PY) -m pytest

.DEFAULT_GOAL := help
.PHONY: help setup setup-full dev test lint typecheck e2e check clean distclean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PY): ## Create the virtualenv
	python3 -m venv $(VENV)
	$(PIP) install -U pip

setup: $(PY) ## Install dev tooling + minimal runtime (enough for `make check`)
	$(PIP) install -r requirements-dev.txt
	@echo "✅ setup complete. Run 'make setup-full' for the heavy runtime (M1+)."

setup-full: setup ## Also install the full runtime stack (langchain, faiss, vectorbt, ...)
	$(PIP) install -r requirements.txt

dev: ## Run the pipeline locally (offline backtest smoke) — needs setup-full from M4
	$(PY) -m src.main --mode backtest --offline

test: ## Run unit tests (excludes e2e)
	$(PYTEST) -m "not e2e" -q

lint: ## Lint with ruff
	$(RUFF) check .

typecheck: ## Type-check with mypy
	$(MYPY) config.py src

e2e: ## Run end-to-end / pipeline smoke tests
	$(PYTEST) -m e2e -q

check: lint typecheck test e2e ## THE gate: lint + typecheck + test + e2e
	@echo "✅ make check passed"

clean: ## Remove caches and generated artifacts (idempotent; keeps .venv + fixtures)
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -rf data/*.parquet data/*.json logs/ faiss_index/ *.faiss
	@echo "✅ clean complete"

distclean: clean ## clean + remove the virtualenv
	rm -rf $(VENV)
