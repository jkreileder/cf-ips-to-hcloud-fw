# system python interpreter. used only to create virtual environment
PY = python3
VENV = venv
BIN=$(VENV)/bin


ifeq ($(OS), Windows_NT)
	BIN=$(VENV)/Scripts
	PY=python
endif


.PHONY: all
all: lint

$(VENV): requirements.txt requirements-dev.txt pyproject.toml
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade -r requirements.txt
	$(BIN)/pip install --upgrade -r requirements-dev.txt
	touch $(VENV)

.PHONY: lint
lint: $(VENV)
	$(BIN)/ruff check .
	$(BIN)/pyright --venvpath .

.PHONY: build
build: $(VENV)
	rm -rf dist
	$(BIN)/python3 -m build

.PHONY: clean
clean:
	rm -rf build dist *.egg-info .ruff_cache $(VENV)
	find . -type f -name *.pyc -delete
	find . -type d -name __pycache__ -delete
