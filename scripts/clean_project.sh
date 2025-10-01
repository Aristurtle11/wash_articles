#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

JSON_PATH="$PROJECT_ROOT/src/settings/default_headers.json"
TEMPLATE_PATH="$PROJECT_ROOT/src/settings/default_headers.template.json"
DATA_DIR="$PROJECT_ROOT/data"

if [[ -e "$JSON_PATH" ]]; then
  echo "Renaming default_headers.json to default_headers.template.json (overwriting existing template)."
  mv -f "$JSON_PATH" "$TEMPLATE_PATH"
elif [[ -e "$TEMPLATE_PATH" ]]; then
  echo "default_headers.json not found; leaving existing template in place."
else
  echo "Neither default_headers.json nor default_headers.template.json exists; nothing to rename."
fi

if [[ -d "$DATA_DIR" ]]; then
  echo "Removing data directory: $DATA_DIR"
  rm -rf "$DATA_DIR"
else
  echo "Data directory not found: $DATA_DIR"
fi

echo "Cleanup complete."
