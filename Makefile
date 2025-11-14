MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

UV := uv
VENV := .venv
BIN := $(VENV)/bin
SYNC_STAMP := $(VENV)/.uv-synced

UV_SYNC_FLAGS := --group dev --frozen
UV_RUN_FLAGS := --no-sync

.PHONY: all
all: lint test build

$(SYNC_STAMP): pyproject.toml uv.lock
	$(UV) sync $(UV_SYNC_FLAGS)
	touch $(SYNC_STAMP)

.PHONY: venv
venv: $(SYNC_STAMP)

.PHONY: sync
sync: $(SYNC_STAMP)

.PHONY: lint
lint: $(SYNC_STAMP)
	$(UV) run $(UV_SYNC_FLAGS) ruff check .
	$(UV) run $(UV_SYNC_FLAGS) pyright --venvpath .

.PHONY: test
test: $(SYNC_STAMP)
	$(UV) $(UV_SYNC_FLAGS) run pytest

.PHONY: check
check: lint test

.PHONY: build
build: $(SYNC_STAMP)
	rm -rf dist
	$(BIN)/python -m build

.PHONY: upgrade-deps
upgrade-deps:
	$(UV) lock --upgrade
	rm -f $(SYNC_STAMP)

.PHONY: clean
clean:
	git clean -xdf
