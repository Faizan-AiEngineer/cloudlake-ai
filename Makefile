PYTHON ?= python

.PHONY: test lint demo build
test:
	$(PYTHON) -m pytest -q
	cd frontend && npm test

lint:
	$(PYTHON) -m ruff check backend data_engineering aws orchestration evaluation/scripts scripts

demo:
	$(PYTHON) -m data_engineering.cli generate --profile demo
	$(PYTHON) -m data_engineering.cli run

build:
	cd frontend && npm ci
	cd frontend && npm run build
