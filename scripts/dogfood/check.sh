#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"

if ! dogfood_token="$(dogfood_read_env_value MOBILE_DOGFOOD_TOKEN "$dogfood_root/.env")" || test -z "$dogfood_token"; then
  echo "MOBILE_DOGFOOD_TOKEN is missing from ignored $dogfood_root/.env" >&2
  exit 1
fi
if ! dogfood_tunnel_url="$(dogfood_read_env_value EXPO_PUBLIC_API_BASE_URL "$dogfood_root/mobile/.env.local")"; then
  echo "EXPO_PUBLIC_API_BASE_URL is missing from ignored mobile/.env.local" >&2
  exit 1
fi
if ! dogfood_write_mobile_env "$dogfood_tunnel_url" "$dogfood_root/mobile/.env.local"; then
  echo "The mobile base URL is not a valid Quick Tunnel URL." >&2
  exit 1
fi

dogfood_check_dir="$(mktemp -d "${TMPDIR:-/tmp}/ai-life-planner-check.XXXXXX")"
trap 'rm -rf "$dogfood_check_dir"' EXIT
dogfood_auth_config="$dogfood_check_dir/curl-auth.conf"
if ! dogfood_write_curl_auth_config "$dogfood_token" "$dogfood_auth_config"; then
  echo "MOBILE_DOGFOOD_TOKEN contains unsupported characters." >&2
  exit 1
fi
unset dogfood_token
dogfood_curl_timeout=(--connect-timeout 5 --max-time 20)
dogfood_curl_resolve=()
dogfood_dns_probe_status=0
curl --silent --show-error --connect-timeout 5 --max-time 5 \
  "$dogfood_tunnel_url/health" >/dev/null 2>&1 || dogfood_dns_probe_status=$?
if test "$dogfood_dns_probe_status" -eq 6; then
  dogfood_resolve_target="$(dogfood_quick_tunnel_resolve_target "$dogfood_tunnel_url" || true)"
  if test -z "$dogfood_resolve_target"; then
    echo "Quick Tunnel hostname is not resolvable." >&2
    exit 1
  fi
  dogfood_curl_resolve=(--resolve "$dogfood_resolve_target")
elif test "$dogfood_dns_probe_status" -ne 0; then
  echo "Quick Tunnel DNS probe failed (curl code $dogfood_dns_probe_status)." >&2
  exit "$dogfood_dns_probe_status"
fi

dogfood_health_code="$(curl "${dogfood_curl_timeout[@]}" "${dogfood_curl_resolve[@]}" --silent --show-error --output "$dogfood_check_dir/health.json" --write-out '%{http_code}' "$dogfood_tunnel_url/health")"
dogfood_today_code="$(curl "${dogfood_curl_timeout[@]}" "${dogfood_curl_resolve[@]}" --silent --show-error --output "$dogfood_check_dir/today.json" --write-out '%{http_code}' --config "$dogfood_auth_config" "$dogfood_tunnel_url/api/v1/today")"
dogfood_missing_code="$(curl "${dogfood_curl_timeout[@]}" "${dogfood_curl_resolve[@]}" --silent --show-error --output /dev/null --write-out '%{http_code}' "$dogfood_tunnel_url/api/v1/today")"
dogfood_invalid_code="$(curl "${dogfood_curl_timeout[@]}" "${dogfood_curl_resolve[@]}" --silent --show-error --output /dev/null --write-out '%{http_code}' -H 'Authorization: Bearer intentionally-invalid' "$dogfood_tunnel_url/api/v1/today")"
dogfood_isolation_code="$(curl "${dogfood_curl_timeout[@]}" "${dogfood_curl_resolve[@]}" --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --config "$dogfood_auth_config" \
  -H 'Content-Type: application/json' \
  --data '{"request_id":"dogfood-script-isolation-check","text":"Проверка изоляции","user_external_id":"somebody-else"}' \
  "$dogfood_tunnel_url/api/v1/capture")"

if test "$dogfood_health_code" != 200 || test "$dogfood_today_code" != 200 || \
  test "$dogfood_missing_code" != 401 || test "$dogfood_invalid_code" != 401 || \
  test "$dogfood_isolation_code" != 422; then
  echo "Dogfood check failed: health=$dogfood_health_code today=$dogfood_today_code missing=$dogfood_missing_code invalid=$dogfood_invalid_code isolation=$dogfood_isolation_code" >&2
  exit 1
fi

TODAY_FILE="$dogfood_check_dir/today.json" "$dogfood_root/.venv/bin/python" - <<'PY'
import json
import os

with open(os.environ["TODAY_FILE"], encoding="utf-8") as source:
    snapshot = json.load(source)

required = {
    "focus_text",
    "progress",
    "scheduled_items",
    "unscheduled_items",
    "completed_items",
    "plan",
    "plan_version",
}
missing = required.difference(snapshot)
if missing:
    raise SystemExit(f"DaySnapshot is missing fields: {sorted(missing)}")

print(
    "Dogfood HTTPS checks passed: "
    f"health=200 today=200 missing=401 invalid=401 isolation=422 "
    f"plan_version={snapshot['plan_version']}"
)
PY
