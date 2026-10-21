#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="${1:-../analytics-engineering/semantic_layer/workspace}"
DEST="${2:-workspace/semantic_layer}"

for package in comics jaffle_shop; do
  if [ ! -f "${SOURCE}/${package}/publisher.json" ]; then
    echo "[error] Missing package: ${SOURCE}/${package}/publisher.json" >&2
    exit 1
  fi
done

mkdir -p "$DEST"

rsync -a --delete \
  "${SOURCE}/" \
  "${DEST}/"

echo "[sync] Copied semantic packages to ${DEST}"
