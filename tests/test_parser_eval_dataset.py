import json
from pathlib import Path

from app.core.config import settings
from app.llm.parser import parse_user_message


CASES_PATH = Path(__file__).parent / "fixtures" / "parser_cases.json"


def _assert_contains_all(actual_values: list[str], expected_values: list[str]) -> None:
    lowered_actual = [value.lower() for value in actual_values]

    for expected in expected_values:
        assert any(expected.lower() in actual for actual in lowered_actual), (
            expected,
            actual_values,
        )


def test_mock_parser_eval_dataset(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    assert len(cases) >= 25

    for case in cases:
        parsed = parse_user_message(case["text"])
        expected = case["expected"]

        assert parsed.intent == expected["intent"], case["text"]

        for field in [
            "date",
            "work_start",
            "work_until",
            "sleep_time",
            "energy_level",
        ]:
            if field in expected:
                assert getattr(parsed, field) == expected[field], case["text"]

        if "goals_contains" in expected:
            _assert_contains_all(parsed.goals, expected["goals_contains"])

        if "tasks_contains" in expected:
            _assert_contains_all([task.title for task in parsed.tasks], expected["tasks_contains"])

        if "task_priorities_contains" in expected:
            _assert_contains_all([task.priority for task in parsed.tasks], expected["task_priorities_contains"])

        if "done_task_title_contains" in expected:
            assert parsed.done_task_title is not None, case["text"]
            assert expected["done_task_title_contains"] in parsed.done_task_title, case["text"]

        if "done_task_titles_contains" in expected:
            _assert_contains_all(parsed.done_task_titles, expected["done_task_titles_contains"])

        if "skipped_task_titles_contains" in expected:
            _assert_contains_all(parsed.skipped_task_titles, expected["skipped_task_titles_contains"])
