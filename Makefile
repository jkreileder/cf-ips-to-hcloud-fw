MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

SYSPYTHON := python3
VENV := venv
BIN := $(VENV)/bin

.PHONY: all
all: lint test build

$(VENV): requirements.txt requirements-dev.txt pyproject.toml
	$(SYSPYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade -r requirements.txt
	$(BIN)/pip install --upgrade -r requirements-dev.txt
	touch $(VENV)

.PHONY: lint
lint: $(VENV)
	$(BIN)/ruff check .
	$(BIN)/pyright --venvpath .

.PHONY: test
test: $(VENV)
	$(BIN)/pytest

.PHONY: check
check: lint test

.PHONY: build
build: $(VENV)
	rm -rf dist
	$(BIN)/python -m build

.PHONY: clean
clean:
	git clean -xdf
