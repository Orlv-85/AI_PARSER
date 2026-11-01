PYTHON ?= ./.venv/bin/python
PYLINT_JOBS ?= 1

.PHONY: help lint lint-ruff lint-mypy lint-pylint

help:
	@echo "Available targets:"
	@echo "  make lint         - run all linters"
	@echo "  make lint-ruff    - run ruff checks"
	@echo "  make lint-mypy    - run mypy type checks"
	@echo "  make lint-pylint  - run pylint"

lint: lint-ruff lint-mypy lint-pylint

lint-ruff:
	$(PYTHON) -m ruff check src tests

lint-mypy:
	$(PYTHON) -m mypy

lint-pylint:
	PYLINTHOME=.pylint.d $(PYTHON) -m pylint --jobs=$(PYLINT_JOBS) src tests
