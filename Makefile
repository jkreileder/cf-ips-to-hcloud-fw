MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

SYSPYTHON := python3
VENV := venv
BIN := $(VENV)/bin

pip-dependencies := requirements.txt requirements-dev.txt
pyproject-dependencies := $(patsubst %.txt,%-pep508.txt,$(pip-dependencies))

.PHONY: all
all: lint test build

$(VENV): pyproject.toml
	$(SYSPYTHON) -m venv $(VENV)
	$(BIN)/pip install --require-hashes -r requirements-dev.txt
	$(BIN)/pip install --require-hashes -r requirements.txt
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
build: $(VENV) $(pyproject-dependencies)
	rm -rf dist
	$(BIN)/python -m build

.PHONY: clean
clean:
	git clean -xdf

requirements.txt: requirements.in
	$(BIN)/pip-compile --no-allow-unsafe --generate-hashes --output-file=requirements.txt requirements.in

requirements-dev.txt: requirements-dev.in
	$(BIN)/pip-compile --allow-unsafe --constraint=requirements.txt --generate-hashes --output-file=requirements-dev.txt requirements-dev.in

$(pyproject-dependencies): %-pep508.txt: %.txt
	$(BIN)/pip-compile --allow-unsafe --output-file=$@ $<
