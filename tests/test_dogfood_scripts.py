from __future__ import annotations

import os
import signal
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "dogfood" / "lib.sh"
START = ROOT / "scripts" / "dogfood" / "start.sh"


def run_lib(
    command: str,
    *args: str,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"; {command}', "bash", str(LIB), *args],
        check=False,
        capture_output=True,
        env={**os.environ, **(env or {})},
        input=input_text,
        text=True,
    )


def test_read_env_value_returns_exact_value_after_first_equals(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=AI Life Planner\nMOBILE_DOGFOOD_TOKEN=abc=def-123\n",
        encoding="utf-8",
    )

    result = run_lib('dogfood_read_env_value MOBILE_DOGFOOD_TOKEN "$2"', str(env_file))

    assert result.returncode == 0
    assert result.stdout == "abc=def-123"
    assert result.stderr == ""


def test_read_env_value_matches_dotenv_last_value_wins_semantics(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MOBILE_DOGFOOD_TOKEN=old-local-value\n"
        "MOBILE_DOGFOOD_TOKEN=current-local-value\n",
        encoding="utf-8",
    )

    result = run_lib('dogfood_read_env_value MOBILE_DOGFOOD_TOKEN "$2"', str(env_file))

    assert result.returncode == 0
    assert result.stdout == "current-local-value"


def test_extract_tunnel_url_accepts_only_exact_quick_tunnel_hostname():
    result = run_lib(
        "dogfood_extract_tunnel_url",
        input_text=(
            "2026-08-10 INF requesting tunnel\n"
            "Visit https://calm-dogfood-day.trycloudflare.com when ready\n"
        ),
    )

    assert result.returncode == 0
    assert result.stdout == "https://calm-dogfood-day.trycloudflare.com\n"


def test_extract_tunnel_url_rejects_suffix_confusion():
    result = run_lib(
        "dogfood_extract_tunnel_url",
        input_text="https://calm-dogfood-day.trycloudflare.com.attacker.example\n",
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_write_mobile_env_rejects_invalid_url_without_overwriting(tmp_path: Path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("EXPO_PUBLIC_API_BASE_URL=https://known-good.example\n", encoding="utf-8")

    result = run_lib(
        'dogfood_write_mobile_env "$2" "$3"',
        "http://127.0.0.1:8000",
        str(env_file),
    )

    assert result.returncode != 0
    assert result.stderr == ""
    assert env_file.read_text(encoding="utf-8") == (
        "EXPO_PUBLIC_API_BASE_URL=https://known-good.example\n"
    )


def test_write_mobile_env_writes_only_public_tunnel_url(tmp_path: Path):
    env_file = tmp_path / ".env.local"

    result = run_lib(
        'dogfood_write_mobile_env "$2" "$3"',
        "https://calm-dogfood-day.trycloudflare.com",
        str(env_file),
    )

    assert result.returncode == 0
    assert env_file.read_text(encoding="utf-8") == (
        "EXPO_PUBLIC_API_BASE_URL=https://calm-dogfood-day.trycloudflare.com\n"
    )


def test_wait_for_health_retries_transient_transport_failure(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    attempt_file = tmp_path / "attempts"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "attempts=0\n"
        "test ! -f \"$DOGFOOD_ATTEMPT_FILE\" || attempts=$(<\"$DOGFOOD_ATTEMPT_FILE\")\n"
        "attempts=$((attempts + 1))\n"
        "printf '%s' \"$attempts\" >\"$DOGFOOD_ATTEMPT_FILE\"\n"
        "test \"$attempts\" -ge 4\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_lib(
        'dogfood_wait_for_health "$2" 6 0',
        "https://calm-dogfood-day.trycloudflare.com/health",
        env={
            "DOGFOOD_ATTEMPT_FILE": str(attempt_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    assert attempt_file.read_text(encoding="utf-8") == "4"


def test_quick_tunnel_health_falls_back_to_direct_a_record(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "curl-args"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" >>\"$DOGFOOD_CURL_ARGS_FILE\"\n"
        "for arg in \"$@\"; do\n"
        "  test \"$arg\" != '--resolve' || exit 0\n"
        "done\n"
        "exit 6\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    fake_dig = fake_bin / "dig"
    fake_dig.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' 104.16.230.132\n",
        encoding="utf-8",
    )
    fake_dig.chmod(0o755)

    result = run_lib(
        'dogfood_curl_health "$2" 5',
        "https://calm-dogfood-day.trycloudflare.com/health",
        env={
            "DOGFOOD_CURL_ARGS_FILE": str(args_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    args = args_file.read_text(encoding="utf-8")
    assert "--resolve" in args
    assert "calm-dogfood-day.trycloudflare.com:443:104.16.230.132" in args


def test_wait_for_health_propagates_child_exit_without_exhausting_retries(
    tmp_path: Path,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    attempt_file = tmp_path / "attempts"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "attempts=0\n"
        "test ! -f \"$DOGFOOD_ATTEMPT_FILE\" || attempts=$(<\"$DOGFOOD_ATTEMPT_FILE\")\n"
        "attempts=$((attempts + 1))\n"
        "printf '%s' \"$attempts\" >\"$DOGFOOD_ATTEMPT_FILE\"\n"
        "sleep 0.1\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_lib(
        '(sleep 0.02; exit 7) & child_pid=$!; '
        'dogfood_wait_for_health_while_process_alive "$2" "$child_pid" 20 0',
        "https://calm-dogfood-day.trycloudflare.com/health",
        env={
            "DOGFOOD_ATTEMPT_FILE": str(attempt_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
    )

    assert result.returncode == 7
    assert attempt_file.read_text(encoding="utf-8") == "1"


def test_warm_ollama_uses_non_thinking_probe_and_long_keep_alive(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "curl-args"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" >\"$DOGFOOD_CURL_ARGS_FILE\"\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    result = run_lib(
        'dogfood_warm_ollama "$2" "$3"',
        "http://127.0.0.1:11434",
        "qwen3.5:4b",
        env={
            "DOGFOOD_CURL_ARGS_FILE": str(args_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    args = args_file.read_text(encoding="utf-8")
    assert '"model":"qwen3.5:4b"' in args
    assert '"think":false' in args
    assert '"num_predict":1' in args
    assert '"keep_alive":"24h"' in args
    assert "http://127.0.0.1:11434/api/chat" in args


def test_warm_ollama_rejects_model_name_that_can_break_json(tmp_path: Path):
    result = run_lib(
        'dogfood_warm_ollama "$2" "$3"',
        "http://127.0.0.1:11434",
        'model"}',
    )

    assert result.returncode != 0
    assert result.stderr == ""


def test_connected_vpn_name_extracts_the_active_service():
    result = run_lib(
        "dogfood_connected_vpn_name",
        input_text=(
            "Available network connection services in the current set (*=enabled):\n"
            '* (Connected) 13D01C45 VPN (org.amnezia.awg) "amnezia_for_awg" '
            "[VPN:org.amnezia.awg]\n"
        ),
    )

    assert result.returncode == 0
    assert result.stdout == "amnezia_for_awg\n"


def test_single_terminal_launcher_help_describes_owned_stack():
    result = subprocess.run(
        [START, "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "одном терминале" in result.stdout
    assert "FastAPI" in result.stdout
    assert "Cloudflare Quick Tunnel" in result.stdout
    assert "Expo" in result.stdout


def test_live_check_keeps_bearer_token_out_of_curl_argv(tmp_path: Path):
    test_root = tmp_path / "project"
    dogfood_dir = test_root / "scripts" / "dogfood"
    shutil.copytree(ROOT / "scripts" / "dogfood", dogfood_dir)
    (test_root / "mobile").mkdir()
    (test_root / "mobile" / ".env.local").write_text(
        "EXPO_PUBLIC_API_BASE_URL=https://calm-dogfood-day.trycloudflare.com\n",
        encoding="utf-8",
    )
    secret = "secret-visible-if-expanded-in-argv"
    (test_root / ".env").write_text(
        f"MOBILE_DOGFOOD_TOKEN={secret}\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    argv_file = tmp_path / "curl-argv"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" >>\"$DOGFOOD_CURL_ARGV_FILE\"\n"
        "url=\"${!#}\"\n"
        "has_valid_auth=0\n"
        "has_invalid_auth=0\n"
        "has_resolve=0\n"
        "has_write_out=0\n"
        "for arg in \"$@\"; do\n"
        "  test \"$arg\" != '--config' || has_valid_auth=1\n"
        f"  test \"$arg\" != 'Authorization: Bearer {secret}' || has_valid_auth=1\n"
        "  test \"$arg\" != 'Authorization: Bearer intentionally-invalid' || has_invalid_auth=1\n"
        "  test \"$arg\" != '--resolve' || has_resolve=1\n"
        "  test \"$arg\" != '--write-out' || has_write_out=1\n"
        "done\n"
        "if [[ \"$url\" == */health ]] && test \"$has_write_out\" -eq 0 && test \"$has_resolve\" -eq 0; then\n"
        "  exit 6\n"
        "fi\n"
        "case \"$url\" in\n"
        "  */health) code=200 ;;\n"
        "  */api/v1/capture) code=422 ;;\n"
        "  */api/v1/today)\n"
        "    if test \"$has_invalid_auth\" -eq 1; then code=401\n"
        "    elif test \"$has_valid_auth\" -eq 1; then code=200\n"
        "    else code=401\n"
        "    fi ;;\n"
        "  *) code=500 ;;\n"
        "esac\n"
        "printf '%s' \"$code\"\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    fake_dig = fake_bin / "dig"
    fake_dig.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' 104.16.230.132\n",
        encoding="utf-8",
    )
    fake_dig.chmod(0o755)

    fake_venv_bin = test_root / ".venv" / "bin"
    fake_venv_bin.mkdir(parents=True)
    fake_python = fake_venv_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\ncat >/dev/null\necho 'validated'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = subprocess.run(
        [dogfood_dir / "check.sh"],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "DOGFOOD_CURL_ARGV_FILE": str(argv_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        text=True,
    )

    assert result.returncode == 0, result.stderr
    curl_argv = argv_file.read_text(encoding="utf-8")
    assert secret not in curl_argv
    assert curl_argv.splitlines().count("--max-time") == 6
    assert curl_argv.splitlines().count("--resolve") == 5


def test_start_mobile_retries_transient_tunnel_health(tmp_path: Path):
    test_root = tmp_path / "project"
    dogfood_dir = test_root / "scripts" / "dogfood"
    shutil.copytree(ROOT / "scripts" / "dogfood", dogfood_dir)
    mobile_dir = test_root / "mobile"
    mobile_dir.mkdir()
    (mobile_dir / "node_modules").mkdir()
    (mobile_dir / ".env.local").write_text(
        "EXPO_PUBLIC_API_BASE_URL=https://calm-dogfood-day.trycloudflare.com\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    attempts_file = tmp_path / "health-attempts"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "attempts=0\n"
        "test ! -f \"$DOGFOOD_ATTEMPT_FILE\" || attempts=$(<\"$DOGFOOD_ATTEMPT_FILE\")\n"
        "attempts=$((attempts + 1))\n"
        "printf '%s' \"$attempts\" >\"$DOGFOOD_ATTEMPT_FILE\"\n"
        "test \"$attempts\" -ge 3\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    fake_dig = fake_bin / "dig"
    fake_dig.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fake_dig.chmod(0o755)
    npm_args_file = tmp_path / "npm-args"
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >\"$DOGFOOD_NPM_ARGS_FILE\"\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)

    result = subprocess.run(
        [dogfood_dir / "start-mobile.sh"],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "DOGFOOD_ATTEMPT_FILE": str(attempts_file),
            "DOGFOOD_NPM_ARGS_FILE": str(npm_args_file),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert attempts_file.read_text(encoding="utf-8") == "3"
    assert npm_args_file.read_text(encoding="utf-8").splitlines() == [
        "start",
        "--",
        "--lan",
    ]


def prepare_fake_supervisor_stack(
    tmp_path: Path,
    *,
    backend_exit_code: int | None = None,
) -> tuple[Path, dict[str, str], Path]:
    test_root = tmp_path / "supervisor-project"
    dogfood_dir = test_root / "scripts" / "dogfood"
    shutil.copytree(ROOT / "scripts" / "dogfood", dogfood_dir)
    (test_root / "mobile").mkdir()

    events_file = tmp_path / "events"
    backend_ready = tmp_path / "backend-ready"
    tunnel_ready = tmp_path / "tunnel-ready"

    if backend_exit_code is None:
        backend_body = (
            "trap 'echo backend-stopped >>\"$DOGFOOD_EVENTS_FILE\"; exit 0' TERM INT\n"
            "echo backend-start >>\"$DOGFOOD_EVENTS_FILE\"\n"
            "touch \"$DOGFOOD_BACKEND_READY\"\n"
            "while :; do sleep 0.05; done\n"
        )
    else:
        backend_body = (
            "echo backend-start >>\"$DOGFOOD_EVENTS_FILE\"\n"
            f"exit {backend_exit_code}\n"
        )
    (dogfood_dir / "start-backend.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + backend_body,
        encoding="utf-8",
    )
    (dogfood_dir / "start-tunnel.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "test -f \"$DOGFOOD_BACKEND_READY\"\n"
        "trap 'echo tunnel-stopped >>\"$DOGFOOD_EVENTS_FILE\"; exit 0' TERM INT\n"
        "echo tunnel-start >>\"$DOGFOOD_EVENTS_FILE\"\n"
        "tunnel_attempts=0\n"
        "if test -n \"${DOGFOOD_TUNNEL_ATTEMPTS_FILE:-}\"; then\n"
        "  test ! -f \"$DOGFOOD_TUNNEL_ATTEMPTS_FILE\" || tunnel_attempts=$(<\"$DOGFOOD_TUNNEL_ATTEMPTS_FILE\")\n"
        "  tunnel_attempts=$((tunnel_attempts + 1))\n"
        "  printf '%s' \"$tunnel_attempts\" >\"$DOGFOOD_TUNNEL_ATTEMPTS_FILE\"\n"
        "fi\n"
        "if test \"${DOGFOOD_FAIL_FIRST_TUNNEL:-0}\" -eq 1; then\n"
        "  test \"$tunnel_attempts\" -ne 1 || exit 9\n"
        "fi\n"
        "sleep \"${DOGFOOD_FAKE_TUNNEL_DELAY:-0}\"\n"
        "printf '%s\\n' 'EXPO_PUBLIC_API_BASE_URL=https://calm-dogfood-day.trycloudflare.com' >\"$DOGFOOD_TEST_ROOT/mobile/.env.local\"\n"
        "touch \"$DOGFOOD_TUNNEL_READY\"\n"
        "if test -n \"${DOGFOOD_TUNNEL_READY_FILE:-}\"; then\n"
        "  printf '%s' 'https://calm-dogfood-day.trycloudflare.com' >\"$DOGFOOD_TUNNEL_READY_FILE\"\n"
        "fi\n"
        "if test \"${DOGFOOD_EXIT_FIRST_TUNNEL_AFTER_READY:-0}\" -eq 1 && test \"$tunnel_attempts\" -eq 1; then\n"
        "  printf '%s' \"$$\" >\"$DOGFOOD_TUNNEL_PID_FILE\"\n"
        "  while test ! -f \"$DOGFOOD_RELEASE_FIRST_TUNNEL\"; do sleep 0.01; done\n"
        "  exit 9\n"
        "fi\n"
        "while :; do sleep 0.05; done\n",
        encoding="utf-8",
    )
    (dogfood_dir / "start-mobile.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "test -f \"$DOGFOOD_BACKEND_READY\"\n"
        "test -f \"$DOGFOOD_TUNNEL_READY\"\n"
        "echo mobile-start >>\"$DOGFOOD_EVENTS_FILE\"\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "supervisor-bin"
    fake_bin.mkdir()
    for command in ("lsof", "pgrep"):
        fake_command = fake_bin / command
        fake_command.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        fake_command.chmod(0o755)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "url=\"${!#}\"\n"
        "case \"$url\" in\n"
        "  http://127.0.0.1:8000/health) test -f \"$DOGFOOD_BACKEND_READY\" ;;\n"
        "  https://calm-dogfood-day.trycloudflare.com/health)\n"
        "    if test \"${DOGFOOD_EXIT_FIRST_TUNNEL_AFTER_READY:-0}\" -eq 1 && test \"$(<\"$DOGFOOD_TUNNEL_ATTEMPTS_FILE\")\" -eq 1; then\n"
        "      touch \"$DOGFOOD_RELEASE_FIRST_TUNNEL\"\n"
        "      tunnel_pid=$(<\"$DOGFOOD_TUNNEL_PID_FILE\")\n"
        "      for _ in $(seq 1 100); do\n"
        "        tunnel_state=$(ps -p \"$tunnel_pid\" -o state= 2>/dev/null || true)\n"
        "        test -n \"$tunnel_state\" && test \"${tunnel_state#*Z}\" != \"$tunnel_state\" && break\n"
        "        sleep 0.01\n"
        "      done\n"
        "    fi\n"
        "    test \"${DOGFOOD_STALE_TUNNEL_HEALTH:-0}\" -eq 1 || test -f \"$DOGFOOD_TUNNEL_READY\" ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    environment = {
        **os.environ,
        "DOGFOOD_BACKEND_READY": str(backend_ready),
        "DOGFOOD_EVENTS_FILE": str(events_file),
        "DOGFOOD_TEST_ROOT": str(test_root),
        "DOGFOOD_TUNNEL_READY": str(tunnel_ready),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    return dogfood_dir / "start.sh", environment, events_file


def test_single_terminal_launcher_starts_in_order_and_cleans_up_owned_processes(
    tmp_path: Path,
):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    unrelated = subprocess.Popen(["sleep", "5"])
    try:
        result = subprocess.run(
            [launcher],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0, result.stderr
        events = events_file.read_text(encoding="utf-8").splitlines()
        assert events[:3] == ["backend-start", "tunnel-start", "mobile-start"]
        assert sorted(events[3:]) == ["backend-stopped", "tunnel-stopped"]
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=2)


def test_single_terminal_launcher_blocks_connected_vpn_before_backend(tmp_path: Path):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    fake_bin = Path(environment["PATH"].split(":", 1)[0])
    fake_scutil = fake_bin / "scutil"
    fake_scutil.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '* (Connected) 13D01C45 VPN (org.amnezia.awg) "
        "\"amnezia_for_awg\" [VPN:org.amnezia.awg]'\n",
        encoding="utf-8",
    )
    fake_scutil.chmod(0o755)

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert not events_file.exists()
    assert "активен vpn «amnezia_for_awg»" in result.stderr.lower()
    assert "DOGFOOD_ALLOW_VPN=1" in result.stderr


def test_single_terminal_launcher_allows_explicit_vpn_override(tmp_path: Path):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    fake_bin = Path(environment["PATH"].split(":", 1)[0])
    fake_scutil = fake_bin / "scutil"
    fake_scutil.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '* (Connected) 13D01C45 VPN (org.amnezia.awg) "
        "\"amnezia_for_awg\" [VPN:org.amnezia.awg]'\n",
        encoding="utf-8",
    )
    fake_scutil.chmod(0o755)
    environment["DOGFOOD_ALLOW_VPN"] = "1"

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert "VPN разрешён явно" in result.stdout
    assert events_file.read_text(encoding="utf-8").splitlines()[:3] == [
        "backend-start",
        "tunnel-start",
        "mobile-start",
    ]


def test_single_terminal_launcher_stops_when_backend_child_fails(tmp_path: Path):
    launcher, environment, events_file = prepare_fake_supervisor_stack(
        tmp_path,
        backend_exit_code=7,
    )

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert events_file.read_text(encoding="utf-8").splitlines() == [
        "backend-start"
    ]
    assert "FastAPI завершился во время запуска" in result.stderr
    assert "unbound variable" not in result.stderr


def test_single_terminal_launcher_ignores_seeded_healthy_stale_tunnel_url(
    tmp_path: Path,
):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    test_root = Path(environment["DOGFOOD_TEST_ROOT"])
    (test_root / "mobile" / ".env.local").write_text(
        "EXPO_PUBLIC_API_BASE_URL=https://calm-dogfood-day.trycloudflare.com\n",
        encoding="utf-8",
    )
    environment["DOGFOOD_FAKE_TUNNEL_DELAY"] = "0.3"
    environment["DOGFOOD_STALE_TUNNEL_HEALTH"] = "1"

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    events = events_file.read_text(encoding="utf-8").splitlines()
    assert events[:3] == ["backend-start", "tunnel-start", "mobile-start"]


def test_single_terminal_launcher_retries_with_a_new_tunnel_after_failure(
    tmp_path: Path,
):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    attempts_file = tmp_path / "tunnel-attempts"
    environment["DOGFOOD_FAIL_FIRST_TUNNEL"] = "1"
    environment["DOGFOOD_TUNNEL_ATTEMPTS_FILE"] = str(attempts_file)

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert attempts_file.read_text(encoding="utf-8") == "2"
    events = events_file.read_text(encoding="utf-8").splitlines()
    assert events[:4] == [
        "backend-start",
        "tunnel-start",
        "tunnel-start",
        "mobile-start",
    ]


def test_single_terminal_launcher_rejects_ready_url_from_exited_tunnel(
    tmp_path: Path,
):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    attempts_file = tmp_path / "tunnel-attempts"
    environment.update(
        {
            "DOGFOOD_EXIT_FIRST_TUNNEL_AFTER_READY": "1",
            "DOGFOOD_RELEASE_FIRST_TUNNEL": str(tmp_path / "release-tunnel"),
            "DOGFOOD_TUNNEL_ATTEMPTS_FILE": str(attempts_file),
            "DOGFOOD_TUNNEL_PID_FILE": str(tmp_path / "tunnel-pid"),
        }
    )

    result = subprocess.run(
        [launcher],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert attempts_file.read_text(encoding="utf-8") == "2"
    events = events_file.read_text(encoding="utf-8").splitlines()
    assert events[:4] == [
        "backend-start",
        "tunnel-start",
        "tunnel-start",
        "mobile-start",
    ]


def test_single_terminal_launcher_restarts_its_recorded_previous_stack(
    tmp_path: Path,
):
    launcher, environment, events_file = prepare_fake_supervisor_stack(tmp_path)
    runtime_dir = tmp_path / "runtime"
    environment["DOGFOOD_RUNTIME_DIR"] = str(runtime_dir)
    mobile_script = launcher.parent / "start-mobile.sh"
    mobile_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "trap 'echo mobile-stopped >>\"$DOGFOOD_EVENTS_FILE\"; exit 0' TERM INT\n"
        "echo mobile-start >>\"$DOGFOOD_EVENTS_FILE\"\n"
        "while :; do sleep 0.05; done\n",
        encoding="utf-8",
    )

    first = subprocess.Popen(
        [launcher],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        for _ in range(100):
            if events_file.exists() and "mobile-start" in events_file.read_text(
                encoding="utf-8"
            ):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("first dogfood stack did not start")

        mobile_script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo mobile-start >>\"$DOGFOOD_EVENTS_FILE\"\n",
            encoding="utf-8",
        )

        second = subprocess.run(
            [launcher],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=5,
        )

        assert second.returncode == 0, second.stderr
        assert "Перезапускаю предыдущий dogfood stack" in second.stdout
        first.wait(timeout=2)
        events = events_file.read_text(encoding="utf-8").splitlines()
        assert events.count("mobile-start") == 2
        assert "mobile-stopped" in events
    finally:
        if first.poll() is None:
            os.killpg(first.pid, signal.SIGTERM)
            first.wait(timeout=2)


def test_launcher_does_not_recover_stack_when_project_runtime_keys_collide(
    tmp_path: Path,
):
    first_area = tmp_path / "first"
    second_area = tmp_path / "second"
    shared_tmp = tmp_path / "shared-tmp"
    first_area.mkdir()
    second_area.mkdir()
    shared_tmp.mkdir()
    first_launcher, first_environment, first_events = prepare_fake_supervisor_stack(
        first_area
    )
    second_launcher, second_environment, _second_events = prepare_fake_supervisor_stack(
        second_area
    )
    first_environment["TMPDIR"] = str(shared_tmp)
    second_environment["TMPDIR"] = str(shared_tmp)
    for environment in (first_environment, second_environment):
        fake_bin = Path(environment["PATH"].split(":", 1)[0])
        fake_cksum = fake_bin / "cksum"
        fake_cksum.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' '12345 99'\n",
            encoding="utf-8",
        )
        fake_cksum.chmod(0o755)
    first_mobile = first_launcher.parent / "start-mobile.sh"
    first_mobile.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "trap 'echo mobile-stopped >>\"$DOGFOOD_EVENTS_FILE\"; exit 0' TERM INT\n"
        "echo mobile-start >>\"$DOGFOOD_EVENTS_FILE\"\n"
        "while :; do sleep 0.05; done\n",
        encoding="utf-8",
    )

    first = subprocess.Popen(
        [first_launcher],
        env=first_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        for _ in range(100):
            if first_events.exists() and "mobile-start" in first_events.read_text(
                encoding="utf-8"
            ):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("first project stack did not start")

        second = subprocess.run(
            [second_launcher],
            check=False,
            capture_output=True,
            env=second_environment,
            text=True,
            timeout=5,
        )

        assert second.returncode != 0
        assert "Перезапускаю предыдущий dogfood stack" not in second.stdout
        assert "другому проекту" in second.stderr
        assert first.poll() is None
        assert "mobile-stopped" not in first_events.read_text(encoding="utf-8")
    finally:
        if first.poll() is None:
            os.killpg(first.pid, signal.SIGTERM)
            first.wait(timeout=2)
