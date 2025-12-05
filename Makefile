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
	$(UV) run $(UV_SYNC_FLAGS) ruff check
	$(UV) run $(UV_SYNC_FLAGS) ty check
	$(UV) run $(UV_SYNC_FLAGS) pyright

.PHONY: test
test: $(SYNC_STAMP)
	$(UV) run $(UV_SYNC_FLAGS) pytest

.PHONY: check
check: lint test

.PHONY: build
build: $(SYNC_STAMP)
	rm -rf dist
	$(UV) build

.PHONY: upgrade-deps
upgrade-deps:
	$(UV) lock --upgrade
	rm -f $(SYNC_STAMP)

.PHONY: clean
clean:
	git clean -xdf
