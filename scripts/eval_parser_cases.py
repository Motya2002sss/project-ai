import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.llm.parser import parse_user_message


CASES_PATH = ROOT_DIR / "tests" / "fixtures" / "parser_cases.json"


def _contains_all(actual_values: list[str], expected_values: list[str]) -> bool:
    lowered_actual = [value.lower() for value in actual_values]

    return all(
        any(expected.lower() in actual for actual in lowered_actual)
        for expected in expected_values
    )


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

    if "task_priorities_contains" in expected:
        priorities = [task.priority for task in parsed.tasks]

        if not _contains_all(priorities, expected["task_priorities_contains"]):
            return False

    if "done_task_title_contains" in expected:
        if not parsed.done_task_title or expected["done_task_title_contains"] not in parsed.done_task_title:
            return False

    if "done_task_titles_contains" in expected:
        if not _contains_all(parsed.done_task_titles, expected["done_task_titles_contains"]):
            return False

    if "skipped_task_titles_contains" in expected:
        if not _contains_all(parsed.skipped_task_titles, expected["skipped_task_titles_contains"]):
            return False

    return True


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = []

    for index, case in enumerate(cases, start=1):
        parsed = parse_user_message(case["text"])
        expected = case["expected"]

        if not _case_passes(parsed, expected):
            failures.append((index, case["text"], expected, parsed.model_dump()))

    total = len(cases)
    passed = total - len(failures)

    print(f"parser eval: {passed}/{total} passed")

    for index, text, expected, actual in failures:
        print(f"\nCase {index} failed")
        print(f"Text: {text}")
        print(f"Expected: {expected}")
        print(f"Actual: {actual}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
