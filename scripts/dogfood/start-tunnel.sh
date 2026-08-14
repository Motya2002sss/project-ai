#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is missing. Install it with: brew install cloudflared" >&2
  exit 1
fi

if ! curl --silent --fail --max-time 5 http://127.0.0.1:8000/health >/dev/null; then
  echo "Backend is not healthy on http://127.0.0.1:8000. Start it first." >&2
  exit 1
fi

dogfood_tunnel_log="$(mktemp "${TMPDIR:-/tmp}/ai-life-planner-cloudflared.XXXXXX")"
dogfood_tunnel_pid=""

trap 'exit 130' INT TERM
trap '
  dogfood_status=$?
  if test -n "$dogfood_tunnel_pid" && kill -0 "$dogfood_tunnel_pid" 2>/dev/null; then
    kill -TERM "$dogfood_tunnel_pid" 2>/dev/null || true
    wait "$dogfood_tunnel_pid" 2>/dev/null || true
  fi
  rm -f "$dogfood_tunnel_log"
  exit "$dogfood_status"
' EXIT

cloudflared tunnel --url http://127.0.0.1:8000 --protocol http2 --no-autoupdate \
  > >(tee "$dogfood_tunnel_log") 2>&1 &
dogfood_tunnel_pid=$!

dogfood_tunnel_url=""
for dogfood_attempt in $(seq 1 60); do
  dogfood_tunnel_url="$(dogfood_extract_tunnel_url <"$dogfood_tunnel_log" || true)"
  if test -n "$dogfood_tunnel_url"; then
    break
  fi
  if ! kill -0 "$dogfood_tunnel_pid" 2>/dev/null; then
    wait "$dogfood_tunnel_pid"
    exit $?
  fi
  sleep 1
done

if test -z "$dogfood_tunnel_url"; then
  echo "Quick Tunnel URL was not assigned within 60 seconds." >&2
  exit 1
fi

if ! dogfood_write_mobile_env "$dogfood_tunnel_url" "$dogfood_root/mobile/.env.local"; then
  echo "Refusing to write an invalid Quick Tunnel URL." >&2
  exit 1
fi

dogfood_health_status=0
dogfood_wait_for_health_while_process_alive \
  "$dogfood_tunnel_url/health" \
  "$dogfood_tunnel_pid" \
  120 \
  1 || dogfood_health_status=$?
if test "$dogfood_health_status" -ne 0; then
  echo "Quick Tunnel stopped or did not become healthy (code $dogfood_health_status)." >&2
  exit "$dogfood_health_status"
fi

if test -n "${DOGFOOD_TUNNEL_READY_FILE:-}"; then
  printf '%s' "$dogfood_tunnel_url" >"$DOGFOOD_TUNNEL_READY_FILE"
fi

echo "Tunnel health passed and mobile/.env.local was updated. Keep this terminal open."
wait "$dogfood_tunnel_pid"
