#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"
cd "$dogfood_root"

for dogfood_command in docker python3 curl; do
  if ! command -v "$dogfood_command" >/dev/null 2>&1; then
    echo "Missing required command: $dogfood_command" >&2
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Open Docker Desktop, then rerun this command." >&2
  exit 1
fi

if ! dogfood_token="$(dogfood_read_env_value MOBILE_DOGFOOD_TOKEN "$dogfood_root/.env")" || test -z "$dogfood_token"; then
  echo "MOBILE_DOGFOOD_TOKEN is missing from ignored $dogfood_root/.env" >&2
  exit 1
fi
unset dogfood_token

if test ! -x "$dogfood_root/.venv/bin/python"; then
  python3 -m venv "$dogfood_root/.venv"
fi

"$dogfood_root/.venv/bin/python" -m pip install -r "$dogfood_root/requirements.txt"
docker compose config >/dev/null
docker compose up -d postgres
"$dogfood_root/.venv/bin/alembic" upgrade head

dogfood_llm_enabled="$(dogfood_read_env_value LLM_ENABLED "$dogfood_root/.env" || true)"
dogfood_llm_provider="$(dogfood_read_env_value LLM_PROVIDER "$dogfood_root/.env" || true)"
if test "$dogfood_llm_enabled" = "true" && test "$dogfood_llm_provider" = "ollama"; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "LLM_PROVIDER=ollama but the ollama command is missing." >&2
    exit 1
  fi

  if ! curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    dogfood_ollama_log="${TMPDIR:-/tmp}/ai-life-planner-ollama.log"
    OLLAMA_KEEP_ALIVE=24h ollama serve >"$dogfood_ollama_log" 2>&1 &
    dogfood_ollama_pid=$!
    for dogfood_attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      if curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        break
      fi
      if ! kill -0 "$dogfood_ollama_pid" 2>/dev/null; then
        echo "Ollama stopped during startup. See $dogfood_ollama_log" >&2
        exit 1
      fi
      sleep 0.5
    done
  fi

  if ! curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama did not become ready on http://127.0.0.1:11434" >&2
    exit 1
  fi

  dogfood_llm_model="$(dogfood_read_env_value LLM_MODEL "$dogfood_root/.env" || true)"
  dogfood_llm_model="${dogfood_llm_model:-qwen3.5:4b}"
  if ! ollama show "$dogfood_llm_model" >/dev/null 2>&1; then
    echo "Configured Ollama model is not installed: $dogfood_llm_model" >&2
    exit 1
  fi
  dogfood_llm_base_url="$(dogfood_read_env_value LLM_BASE_URL "$dogfood_root/.env" || true)"
  dogfood_llm_base_url="${dogfood_llm_base_url:-http://127.0.0.1:11434}"
  if ! dogfood_warm_ollama "$dogfood_llm_base_url" "$dogfood_llm_model"; then
    echo "Ollama model prewarm failed: $dogfood_llm_model" >&2
    exit 1
  fi
  echo "Ollama parser is warm and ready ($dogfood_llm_model)."
fi

echo "Backend prerequisites are ready. Starting FastAPI on http://127.0.0.1:8000"
exec "$dogfood_root/.venv/bin/uvicorn" app.mobile_dogfood:app --host 127.0.0.1 --port 8000
