# PHC SupplySignal — common commands. Run `make` to list them.
# Uses uv when available (fast installs) and falls back to pip.

PYTHON  ?= python3.13
VENV    := .venv
PY      := $(VENV)/bin/python
UV      := $(shell command -v uv 2>/dev/null)
EXTRAS  := app,model,dev,notebook
BROWSER ?=
SMOKE_PORT := 8502
SMOKE_NAME := supplysignal-smoke

.DEFAULT_GOAL := help
.PHONY: help app up down setup run pipeline test smoke lint notebooks clean

help: ## List the available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

app: ## Build and start the app with Docker at http://localhost:8501
	docker compose up --build

up: ## Build and start the app in the background
	docker compose up --build -d

down: ## Stop the app (keeps saved observations)
	docker compose down

setup: ## Create .venv and install the project with pinned versions
ifdef UV
	@test -x $(PY) || uv venv --python 3.13 $(VENV)
	uv pip install --python $(PY) -c requirements-executed.txt -e '.[$(EXTRAS)]'
else
	@test -x $(PY) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -c requirements-executed.txt -e '.[$(EXTRAS)]'
endif

pipeline: ## Generate data, train the model and build the worklist
	@test -f data/raw/afijio_public_primary_arcgis.json || \
		(mkdir -p data/raw && cp data/snapshots/afijio_public_primary_arcgis.json data/raw/)
	$(PY) -m supplysignal.pipeline
	$(PY) -m supplysignal.baseline
	$(PY) -m supplysignal.train
	$(PY) -m supplysignal.inference
	$(PY) -m supplysignal.ranking_eval
	$(PY) -m supplysignal.workload_eval
	$(PY) -m supplysignal.decisions

run: ## Run the app locally without Docker (run `make pipeline` first)
	$(PY) -m streamlit run app/main.py

test: ## Run the unit tests
	$(PY) -m unittest discover -s tests -v

lint: ## Check for errors with ruff
	$(PY) -m ruff check --select E9,F63,F7,F82 src app tests

notebooks: ## Re-run all five notebooks in order and save their outputs
	@for nb in notebooks/0*.ipynb; do $(PY) scripts/execute_notebook.py "$$nb" || exit 1; done

smoke: ## Browser test against a disposable container (BROWSER=<chromium path> optional)
	docker build -t $(SMOKE_NAME) .
	$(if $(BROWSER),,$(PY) -m playwright install chromium)
	docker run --rm -d --name $(SMOKE_NAME) -p 127.0.0.1:$(SMOKE_PORT):8501 $(SMOKE_NAME)
	@sleep 8
	$(PY) tests/browser_smoke.py --url http://127.0.0.1:$(SMOKE_PORT) $(if $(BROWSER),--browser-executable $(BROWSER)) ; \
		status=$$?; docker stop $(SMOKE_NAME) >/dev/null; exit $$status

clean: ## Remove caches (keeps .venv, data and the Docker volume)
	find . -name __pycache__ -not -path './$(VENV)/*' -prune -exec rm -rf {} +
	rm -rf .ruff_cache .pytest_cache src/*.egg-info
