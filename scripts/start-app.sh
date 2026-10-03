#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f "$HOME/.nvm/nvm.sh" ]; then
  # npm exports its prefix when invoking scripts; nvm rejects that override.
  unset npm_config_prefix NPM_CONFIG_PREFIX
  # shellcheck disable=SC1090
  source "$HOME/.nvm/nvm.sh"
  nvm use 20 >/dev/null
fi

node scripts/start.js "$@"
