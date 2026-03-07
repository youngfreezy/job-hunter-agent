#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/JobHunter Agent.app"
TARGET_DIR="${1:-$HOME/Applications}"
TARGET="$TARGET_DIR/JobHunter Agent.app"

mkdir -p "$TARGET_DIR"
rm -rf "$TARGET"
cp -R "$APP" "$TARGET"

printf 'Installed macOS app bundle to %s\n' "$TARGET"
