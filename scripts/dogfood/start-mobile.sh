#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is missing." >&2
  exit 1
fi

if ! dogfood_tunnel_url="$(dogfood_read_env_value EXPO_PUBLIC_API_BASE_URL "$dogfood_root/mobile/.env.local")"; then
  echo "mobile/.env.local is missing. Start the Quick Tunnel first." >&2
  exit 1
fi

if ! dogfood_write_mobile_env "$dogfood_tunnel_url" "$dogfood_root/mobile/.env.local"; then
  echo "mobile/.env.local does not contain a valid Quick Tunnel URL." >&2
  exit 1
fi

if ! dogfood_wait_for_health "$dogfood_tunnel_url/health" 6 1; then
  echo "The configured HTTPS backend is not healthy. Restart the Quick Tunnel." >&2
  exit 1
fi

cd "$dogfood_root/mobile"
if test ! -d node_modules; then
  npm ci
fi

echo "Starting Expo in LAN mode. Scan the QR with the iPhone Camera or Expo Go."
exec npm start -- --lan
