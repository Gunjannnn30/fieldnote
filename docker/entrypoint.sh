#!/usr/bin/env bash
# Build the corpus and the index on first start, then serve.
set -euo pipefail

DATA_DIR="${FIELDNOTE_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"
export FIELDNOTE_DATA_DIR="$DATA_DIR"

if [ ! -f "$DATA_DIR/artifacts/manifest.jsonl" ]; then
  echo "[fieldnote] first start: rendering the corpus and building the index."
  echo "[fieldnote] this takes a few minutes; the service starts when it is done."
  fieldnote build
  fieldnote ingest
  fieldnote index
fi

exec "$@"
