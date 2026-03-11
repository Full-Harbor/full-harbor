# Ask a Sailor — Makefile
# Usage: make seed | make serve | make test

PYTHON     := python3
SRC        := src
PYTHONPATH := $(CURDIR)/$(SRC)
CLUB       ?= all
CORPUS_DIR ?= /tmp/full-harbor/corpus
PORT       ?= 8000

.PHONY: seed serve test

## Seed the corpus from structured audit data (no network, no OpenAI key required)
seed:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(SRC)/ingestion/ingest_club_content.py \
		--club $(CLUB) \
		--sources structured \
		--output-dir $(CORPUS_DIR)

## Start the FastAPI server
serve:
	PYTHONPATH=$(PYTHONPATH) uvicorn api.main:app \
		--host 0.0.0.0 \
		--port $(PORT) \
		--app-dir $(SRC)

## Run the test suite (corpus-presence tests; skips integration tests)
test:
	cd ../.. && PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest packages/ask-a-sailor/tests/ -v -m "not integration"
