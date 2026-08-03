import argparse
import json
import re
import sys
from pathlib import Path
from time import perf_counter

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.llm.parser import parse_user_message


CASES_PATH = ROOT_DIR / "tests" / "fixtures" / "parser_cases.json"
RU_SUFFIXES = [
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ыми",
    "ими",
    "ией",
    "ия",
    "ий",
    "ый",
    "ой",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ую",
    "юю",
    "ом",
    "ем",
    "ах",
    "ях",
    "ов",
    "ев",
    "ам",
    "ям",
    "а",
    "я",
    "ы",
    "и",
    "у",
    "ю",
    "е",
    "о",
]


def _normalize_match_text(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def _stem_ru_token(token: str) -> str:
    if len(token) <= 4:
        return token

    for suffix in RU_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]

    return token


def _match_tokens(value: str) -> set[str]:
    normalized = _normalize_match_text(value)

    return {
        _stem_ru_token(token)
        for token in normalized.split()
        if len(token) > 2
    }


def _soft_text_match(actual: str, expected: str) -> bool:
    actual_normalized = _normalize_match_text(actual)
    expected_normalized = _normalize_match_text(expected)

    if not actual_normalized or not expected_normalized:
        return False

    if expected_normalized in actual_normalized or actual_normalized in expected_normalized:
        return True

    actual_tokens = _match_tokens(actual_normalized)
    expected_tokens = _match_tokens(expected_normalized)

    if not actual_tokens or not expected_tokens:
        return False

    overlap = actual_tokens & expected_tokens

    if len(overlap) == len(expected_tokens):
        return True

    return len(overlap) / len(expected_tokens) >= 0.5


def _contains_all(actual_values: list[str], expected_values: list[str]) -> bool:
    return all(
        any(_soft_text_match(actual, expected) for actual in actual_values)
        for expected in expected_values
    )


def _tasks_match(actual_tasks, expected_tasks: list[dict]) -> bool:
    for expected_task in expected_tasks:
        title_contains = expected_task.get("title_contains")
        matched = False

        for actual_task in actual_tasks:
            if title_contains and not _soft_text_match(actual_task.title, title_contains):
                continue

            if all(
                getattr(actual_task, field) == expected_value
                for field, expected_value in expected_task.items()
                if field != "title_contains"
            ):
                matched = True
                break

        if not matched:
            return False

    return True


def _case_passes(parsed, expected: dict) -> bool:
    if parsed.intent != expected["intent"]:
        return False

    for field in [
        "date",
        "work_start",
        "work_until",
        "sleep_time",
        "energy_level",
    ]:
        if field in expected and getattr(parsed, field) != expected[field]:
            return False

    if "goals_contains" in expected and not _contains_all(parsed.goals, expected["goals_contains"]):
        return False

    if "tasks_contains" in expected:
        titles = [task.title for task in parsed.tasks]

        if not _contains_all(titles, expected["tasks_contains"]):
            return False

    if "tasks_count" in expected and len(parsed.tasks) != expected["tasks_count"]:
        return False

    if "task_titles_exclude" in expected:
        excluded = [_normalize_match_text(value) for value in expected["task_titles_exclude"]]

        if any(
            token and token in _normalize_match_text(task.title)
            for task in parsed.tasks
            for token in excluded
        ):
            return False

    if "tasks_match" in expected and not _tasks_match(parsed.tasks, expected["tasks_match"]):
        return False

    if "task_priorities_contains" in expected:
        priorities = [task.priority for task in parsed.tasks]

        if not _contains_all(priorities, expected["task_priorities_contains"]):
            return False

    if "done_task_title_contains" in expected:
        if not parsed.done_task_title:
            return False

        if not _soft_text_match(parsed.done_task_title, expected["done_task_title_contains"]):
            return False

    if "done_task_titles_contains" in expected:
        if not _contains_all(parsed.done_task_titles, expected["done_task_titles_contains"]):
            return False

    if "skipped_task_titles_contains" in expected:
        if not _contains_all(parsed.skipped_task_titles, expected["skipped_task_titles_contains"]):
            return False

    return True


def evaluate_cases(cases: list[dict], strict_llm: bool) -> dict:
    failures = []
    fallback_count = 0
    latencies_ms = []
    model = settings.llm_model if settings.llm_enabled and settings.llm_provider != "mock" else "mock"

    for index, case in enumerate(cases, start=1):
        started_at = perf_counter()
        parsed = parse_user_message(case["text"])
        latencies_ms.append((perf_counter() - started_at) * 1000)
        expected = case["expected"]
        used_fallback = parsed.used_fallback

        if used_fallback:
            fallback_count += 1

        failed_by_expected_shape = not _case_passes(parsed, expected)
        failed_by_strict_fallback = strict_llm and settings.llm_enabled and used_fallback

        if failed_by_expected_shape or failed_by_strict_fallback:
            reason = "fallback" if failed_by_strict_fallback else "expected_shape"
            failures.append((index, case["text"], reason, expected, parsed.model_dump()))

    total = len(cases)
    passed = total - len(failures)
    sorted_latencies = sorted(latencies_ms)
    p95_index = max(0, min(len(sorted_latencies) - 1, round(len(sorted_latencies) * 0.95) - 1))

    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "fallback_count": fallback_count,
        "provider": settings.llm_provider,
        "model": model or "mock",
        "strict_llm": strict_llm,
        "latency_total_seconds": sum(latencies_ms) / 1000,
        "latency_avg_ms": sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0,
        "latency_p95_ms": sorted_latencies[p95_index] if sorted_latencies else 0,
        "failures": failures,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate parser behavior against fixture cases.")
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="Fail cases when LLM is enabled and parser falls back to mock.",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    strict_llm = args.strict_llm or settings.llm_eval_strict
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    result = evaluate_cases(cases, strict_llm=strict_llm)

    print("parser eval summary")
    print(f"provider: {result['provider']}")
    print(f"model: {result['model']}")
    print(f"strict_llm: {result['strict_llm']}")
    print(f"total cases: {result['total']}")
    print(f"passed: {result['passed']}")
    print(f"failed: {result['failed']}")
    print(f"fallback_count: {result['fallback_count']}")
    print(f"latency_total_seconds: {result['latency_total_seconds']:.3f}")
    print(f"latency_avg_ms: {result['latency_avg_ms']:.1f}")
    print(f"latency_p95_ms: {result['latency_p95_ms']:.1f}")

    for index, text, reason, expected, actual in result["failures"]:
        print(f"\nCase {index} failed")
        print(f"Reason: {reason}")
        print(f"Text: {text}")
        print(f"Expected: {expected}")
        print(f"Actual: {actual}")

    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
