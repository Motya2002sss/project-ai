#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"

if ! command -v pbcopy >/dev/null 2>&1; then
  echo "pbcopy is unavailable on this machine." >&2
  exit 1
fi

if ! dogfood_token="$(dogfood_read_env_value MOBILE_DOGFOOD_TOKEN "$dogfood_root/.env")" || test -z "$dogfood_token"; then
  echo "MOBILE_DOGFOOD_TOKEN is missing from ignored $dogfood_root/.env" >&2
  exit 1
fi

printf '%s' "$dogfood_token" | pbcopy
unset dogfood_token
echo "Dogfood token copied to the clipboard."
