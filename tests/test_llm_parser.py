import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.llm import parser
from app.llm.schemas import ParsedUserMessage


def test_mock_parser_works_without_llm_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    parsed = parser.parse_user_message("Завтра хочу позаниматься математикой")

    assert parsed.intent == "add_tasks"
    assert parsed.date == "tomorrow"
    assert parsed.tasks
    assert parsed.tasks[0].title == "позаниматься математикой"


def test_llm_parser_falls_back_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def raise_llm_error(text: str, provider: str):
        raise RuntimeError("simulated llm outage")

    monkeypatch.setattr(parser, "_parse_with_llm", raise_llm_error)

    parsed = parser.parse_user_message("Что сделать для целей?")

    assert parsed.intent == "suggest_goal_tasks"
    assert parsed.used_fallback is True
    assert parsed.fallback_reason == "RuntimeError"


def test_llm_parser_logs_safe_warning_on_fallback(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def raise_llm_error(text: str, provider: str):
        raise RuntimeError("provider failed with test-key and sk-secret")

    monkeypatch.setattr(parser, "_parse_with_llm", raise_llm_error)
    caplog.set_level(logging.WARNING, logger="app.llm.parser")

    parsed = parser.parse_user_message("Покажи план завтра")

    assert parsed.intent == "show_plan"
    assert "LLM parser fallback to mock" in caplog.text
    assert "provider=openai" in caplog.text
    assert "test-key" not in caplog.text
    assert "sk-secret" not in caplog.text
    assert "sk-[redacted]" in caplog.text


def test_llm_parser_returns_mocked_llm_json(monkeypatch):
    create_calls = []

    class FakeOpenAI:
        def __init__(self, api_key, base_url=None, timeout=None, max_retries=None):
            assert api_key == "test-key"
            assert base_url == "http://localhost:11434/v1"
            assert timeout == 7
            assert max_retries == 0
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create_completion)
            )

        def _create_completion(self, **kwargs):
            create_calls.append(kwargs)
            content = json.dumps(
                {
                    "intent": "add_tasks",
                    "date": "tomorrow",
                    "energy_level": "medium",
                    "tasks": [
                        {
                            "title": "составить семейный бюджет",
                            "priority": "high",
                            "estimated_minutes": 45,
                        }
                    ],
                }
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=content)
                    )
                ]
            )

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "llm_model", "local-model")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 7)
    monkeypatch.setattr(settings, "llm_max_output_tokens", 123)
    monkeypatch.setattr(parser, "OpenAI", FakeOpenAI)

    parsed = parser.parse_user_message("Завтра хочу разобраться с семейным бюджетом")

    assert parsed.intent == "add_tasks"
    assert parsed.date == "tomorrow"
    assert parsed.energy_level == "medium"
    assert parsed.tasks[0].title == "составить семейный бюджет"
    assert parsed.tasks[0].priority == "high"
    assert parsed.tasks[0].estimated_minutes == 45
    assert parsed.raw_text == "Завтра хочу разобраться с семейным бюджетом"
    assert parsed.parser_provider == "openai-compatible"
    assert parsed.used_fallback is False
    assert create_calls[0]["model"] == "local-model"
    assert create_calls[0]["max_tokens"] == 123
    assert create_calls[0]["response_format"] == {"type": "json_object"}


def test_llm_parser_falls_back_when_input_is_too_long(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_max_input_chars", 10)
    caplog.set_level(logging.WARNING, logger="app.llm.parser")

    parsed = parser.parse_user_message("Завтра хочу спокойно почитать книгу")

    assert parsed.intent == "add_tasks"
    assert parsed.date == "tomorrow"
    assert parsed.used_fallback is True
    assert parsed.fallback_reason == "LLMInputTooLongError"
    assert "LLMInputTooLongError" in caplog.text


def test_ollama_provider_returns_mocked_native_json(monkeypatch):
    post_calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "intent": "update_goals",
                            "goals": ["вести семейный бюджет", "больше читать"],
                        }
                    )
                }
            }

    class FakeHttpxClient:
        def __init__(self, timeout=None):
            assert timeout.connect == 3
            assert timeout.read == 11

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json):
            post_calls.append((url, json))
            return FakeResponse()

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://192.168.1.7:11434")
    monkeypatch.setattr(settings, "llm_model", "qwen3.5:4b")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 11)
    monkeypatch.setattr(settings, "llm_max_output_tokens", 222)
    monkeypatch.setattr(settings, "llm_ollama_think", False)
    monkeypatch.setattr(parser.httpx, "Client", FakeHttpxClient)

    parsed = parser.parse_user_message("Мои цели: вести семейный бюджет и больше читать")

    assert parsed.intent == "update_goals"
    assert parsed.goals == ["вести семейный бюджет", "больше читать"]
    assert parsed.parser_provider == "ollama"
    assert parsed.used_fallback is False
    assert post_calls[0][0] == "http://192.168.1.7:11434/api/chat"
    assert post_calls[0][1]["model"] == "qwen3.5:4b"
    assert post_calls[0][1]["think"] is False
    assert post_calls[0][1]["stream"] is False
    assert post_calls[0][1]["options"]["num_predict"] == 222
    assert post_calls[0][1]["options"]["temperature"] == 0


def test_ollama_empty_content_falls_back_in_normal_mode(monkeypatch, caplog):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": ""}}

    class FakeHttpxClient:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "llm_model", "qwen3.5:4b")
    monkeypatch.setattr(parser.httpx, "Client", FakeHttpxClient)
    caplog.set_level(logging.WARNING, logger="app.llm.parser")

    parsed = parser.parse_user_message("Покажи план завтра")

    assert parsed.intent == "show_plan"
    assert parsed.date == "tomorrow"
    assert parsed.parser_provider == "mock"
    assert parsed.used_fallback is True
    assert parsed.fallback_reason == "RuntimeError"
    assert "Empty LLM response" in caplog.text


def test_llm_content_normalizes_short_time_values_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "update_profile",
                "work_start": "8",
                "work_until": "20",
                "sleep_time": "08",
            }
        ),
        text="Мой график с 8 до 20, сон в 08",
    )

    assert parsed.work_start == "08:00"
    assert parsed.work_until == "20:00"
    assert parsed.sleep_time == "08:00"


def test_llm_content_normalizes_adaptive_task_fields():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "созвон",
                        "operation": "create",
                        "scheduling_type": "fixed",
                        "target_date": "2026-08-04",
                        "fixed_start": "9",
                        "fixed_end": "10",
                        "priority": "high",
                        "estimated_minutes": 60,
                        "ignored_technical_field": "drop database",
                    }
                ],
            }
        ),
        text="Завтра в 9 созвон на час",
    )

    task = parsed.tasks[0]
    assert task.fixed_start == "09:00"
    assert task.fixed_end == "10:00"
    assert task.scheduling_type == "fixed"
    assert not hasattr(task, "ignored_technical_field")


def test_parsed_task_rejects_invalid_operation_and_time():
    with pytest.raises(ValidationError):
        ParsedUserMessage.model_validate(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "задача",
                        "operation": "execute_shell",
                    }
                ],
            }
        )

    with pytest.raises(ValidationError):
        ParsedUserMessage.model_validate(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "задача",
                        "scheduling_type": "fixed",
                        "fixed_start": "25:00",
                    }
                ],
            }
        )


def test_llm_fixed_event_uses_deterministic_title_and_date_metadata():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "Тенnis",
                        "operation": "create",
                        "scheduling_type": "fixed",
                        "target_date": "today",
                        "fixed_start": "19:00",
                    }
                ],
            }
        ),
        text="Я записался на теннис в 19:00",
    )

    assert parsed.tasks[0].title == "теннис"
    assert parsed.tasks[0].target_date is None


def test_llm_empty_task_title_is_filled_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "",
                        "operation": "create",
                    }
                ],
            }
        ),
        text="Сегодня хочу разобрать документы",
    )

    assert parsed.tasks[0].title == "разобрать документы"


def test_llm_unjustified_unscheduled_task_uses_deterministic_flexible_fallback():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "date": "today",
                "tasks": [
                    {
                        "title": "Теннис",
                        "operation": "create",
                        "scheduling_type": "unscheduled",
                    }
                ],
            }
        ),
        text="Сегодня добавь теннис на час",
    )

    assert parsed.tasks[0].scheduling_type == "flexible"
    assert parsed.tasks[0].estimated_minutes == 60


def test_llm_content_normalizes_null_lists_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "show_plan",
                "tasks": None,
                "goals": None,
                "done_task_titles": None,
                "skipped_task_titles": None,
            }
        ),
        text="Покажи план",
    )

    assert parsed.tasks == []
    assert parsed.goals == []
    assert parsed.done_task_titles == []
    assert parsed.skipped_task_titles == []


def test_llm_content_normalizes_string_null_values_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "show_plan",
                "date": "null",
                "energy_level": "none",
                "tasks": "null",
                "goals": "null",
                "done_task_titles": "null",
                "skipped_task_titles": "none",
            }
        ),
        text="Покажи план",
    )

    assert parsed.date is None
    assert parsed.energy_level is None
    assert parsed.tasks == []
    assert parsed.goals == []
    assert parsed.done_task_titles == []
    assert parsed.skipped_task_titles == []


def test_llm_content_normalizes_null_task_priority_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "разобрать документы",
                        "priority": None,
                        "estimated_minutes": 30,
                    }
                ],
            }
        ),
        text="Сегодня хочу разобрать документы",
    )

    assert parsed.tasks[0].priority == "medium"


def test_llm_content_normalizes_string_null_task_priority_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "разобрать документы",
                        "priority": "null",
                        "estimated_minutes": 30,
                    }
                ],
            }
        ),
        text="Сегодня хочу разобрать документы",
    )

    assert parsed.tasks[0].priority == "medium"


def test_llm_content_extracts_json_from_extra_text():
    parsed = parser._parse_llm_content(
        'Ответ:\n```json\n{"intent": "show_tasks", "date": "today"}\n```',
        text="Какие задачи на сегодня?",
    )

    assert parsed.intent == "show_tasks"
    assert parsed.date == "today"


def test_llm_content_polishes_goal_progress_intent_and_date():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "show_plan",
                "date": None,
                "tasks": [],
            }
        ),
        text="Как продвинуться по целям завтра?",
    )

    assert parsed.intent == "suggest_goal_tasks"
    assert parsed.date == "tomorrow"


def test_llm_content_polishes_mixed_text_date_and_task_priority():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "date": None,
                "energy_level": None,
                "tasks": [
                    {
                        "title": "подготовиться к экзамену",
                        "priority": "medium",
                        "estimated_minutes": 60,
                    }
                ],
            }
        ),
        text="Сегодня мало сил, планирую подготовиться к экзамену",
    )

    assert parsed.date == "today"
    assert parsed.energy_level == "low"
    assert parsed.tasks[0].priority == "high"


def test_llm_content_removes_hallucinated_date_when_text_has_no_date():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "date": "today",
                "tasks": [
                    {
                        "title": "подготовка к экзамену",
                        "priority": "high",
                        "estimated_minutes": 60,
                    }
                ],
            }
        ),
        text="Планирую подготовиться к экзамену",
    )

    assert parsed.date is None
    assert parsed.tasks[0].priority == "high"


def test_llm_content_polishes_missing_daily_summary_skipped_titles():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "daily_summary",
                "done_task_titles": ["купил продукты"],
                "skipped_task_titles": [],
            }
        ),
        text="Итоги дня: купил продукты, не успел бюджет",
    )

    assert "купил продукты" in parsed.done_task_titles
    assert "бюджет" in parsed.skipped_task_titles


def test_llm_content_polishes_day_availability_intent_over_profile():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "update_profile",
                "work_until": "19",
            }
        ),
        text="Работаю до 19",
    )

    assert parsed.intent == "set_day_availability"
    assert parsed.work_context == "day"
    assert parsed.work_until == "19:00"


@pytest.mark.parametrize(
    ("text", "intent", "work_context", "work_start", "work_until", "task_count"),
    [
        ("Я работаю с 9 до 18", "set_work_schedule", "permanent", "09:00", "18:00", 0),
        ("Сегодня работаю с 10 до 19", "set_day_availability", "day", "10:00", "19:00", 0),
        ("По будням работаю с 9 до 18", "set_work_schedule", "permanent", "09:00", "18:00", 0),
        ("Добавь рабочую задачу на час", "create_task", None, None, None, 1),
        ("В 15:00 рабочий созвон", "create_event", None, None, None, 1),
        ("Внести работу с 9 до 18", "set_work_schedule", "ambiguous", "09:00", "18:00", 0),
        ("Добавь работу с 9 до 18", "set_work_schedule", "ambiguous", "09:00", "18:00", 0),
        ("Я сегодня не работаю", "set_day_availability", "off", None, None, 0),
        ("Сегодня рабочий день до 20", "set_day_availability", "day", None, "20:00", 0),
    ],
)
def test_work_messages_have_distinct_semantics(
    monkeypatch,
    text,
    intent,
    work_context,
    work_start,
    work_until,
    task_count,
):
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")

    parsed = parser.parse_user_message(text)

    assert parsed.intent == intent
    assert parsed.work_context == work_context
    assert parsed.work_start == work_start
    assert parsed.work_until == work_until
    assert len(parsed.tasks) == task_count


def test_llm_content_repairs_invalid_operation_intent_before_validation():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "update",
                "tasks": [
                    {
                        "title": "проект",
                        "operation": "update",
                        "duration_delta_minutes": 40,
                    }
                ],
            }
        ),
        text="Добавь ещё 40 минут на проект",
    )

    assert parsed.intent == "add_tasks"
    assert parsed.tasks[0].operation == "update"
    assert parsed.tasks[0].title == "проект"


def test_llm_complete_task_populates_legacy_done_title():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "mark_done",
                "tasks": [
                    {
                        "title": "подготовку",
                        "operation": "complete",
                        "referenced_task_title": "подготовку",
                    }
                ],
            }
        ),
        text="Отметь подготовку как готово",
    )

    assert parsed.done_task_title == "подготовку"


def test_llm_content_polishes_mixed_profile_text_without_hallucinated_tasks():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "date": None,
                "energy_level": "low",
                "tasks": [
                    {
                        "title": "выдуманная задача",
                        "priority": "high",
                        "estimated_minutes": 60,
                    }
                ],
            }
        ),
        text="Я обычно работаю весь день, вечером сил мало. Хочу подтянуть финансы и учебу. Сегодня могу выделить часа два.",
    )

    assert parsed.intent == "update_profile"
    assert parsed.date == "today"
    assert parsed.energy_level == "low"
    assert parsed.tasks == []


@pytest.mark.parametrize(
    "text",
    [
        "Сделай отдельный трекер питания",
        "Оставь только главное",
    ],
)
def test_llm_content_does_not_turn_capabilities_or_day_context_into_tasks(text: str):
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": text,
                        "operation": "create",
                        "scheduling_type": "flexible",
                        "estimated_minutes": 60,
                    }
                ],
            }
        ),
        text=text,
    )

    assert parsed.intent == "add_tasks"
    assert parsed.tasks == []


def test_llm_content_uses_deterministic_routine_semantics():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "update_profile",
                "tasks": [
                    {
                        "title": "учить английский",
                        "operation": "create",
                        "scheduling_type": "unscheduled",
                        "preferred_window": "evening",
                        "recurrence_hint": "по будням",
                    }
                ],
            }
        ),
        text="По будням учить английский вечером",
    )

    assert parsed.intent == "add_tasks"
    assert parsed.tasks[0].recurrence_hint == "по будням"
    assert parsed.tasks[0].preferred_window == "evening"


def test_llm_content_keeps_explicit_duration_task_flexible():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "Работа над проектом",
                        "operation": "create",
                        "scheduling_type": "unscheduled",
                        "estimated_minutes": 40,
                        "needs_clarification": True,
                        "clarification_reason": "missing_time_and_target",
                    }
                ],
            }
        ),
        text="Проект 40 минут",
    )

    assert parsed.tasks[0].scheduling_type == "flexible"
    assert parsed.tasks[0].estimated_minutes == 40
    assert parsed.tasks[0].needs_clarification is False
    assert parsed.tasks[0].clarification_reason is None


def test_llm_content_splits_multi_action_into_deterministic_operations():
    parsed = parser._parse_llm_content(
        json.dumps(
            {
                "intent": "add_tasks",
                "date": "tomorrow",
                "tasks": [
                    {
                        "title": "Зал и созвон",
                        "operation": "cancel",
                        "target_date": "tomorrow",
                    }
                ],
            }
        ),
        text="Зал отменяется, в 19 созвон, проект перенеси на завтра",
    )

    assert parsed.date is None
    assert [task.operation for task in parsed.tasks] == ["cancel", "create", "update"]
    assert parsed.tasks[0].referenced_task_title == "Зал"
    assert parsed.tasks[1].fixed_start == "19:00"
    assert parsed.tasks[2].target_date == "tomorrow"
    assert parsed.tasks[2].referenced_task_title == "проект"


def test_parsed_user_message_accepts_valid_llm_shape():
    parsed = ParsedUserMessage.model_validate(
        {
            "intent": "add_tasks",
            "date": "today",
            "energy_level": "low",
            "tasks": [
                {
                    "title": "разобрать документы",
                    "priority": "medium",
                    "estimated_minutes": 45,
                }
            ],
        }
    )

    assert parsed.intent == "add_tasks"
    assert parsed.date == "today"
    assert parsed.energy_level == "low"
    assert parsed.tasks[0].priority == "medium"


def test_parsed_user_message_rejects_unsafe_or_invalid_values():
    with pytest.raises(ValidationError):
        ParsedUserMessage.model_validate({"intent": "delete_database"})

    with pytest.raises(ValidationError):
        ParsedUserMessage.model_validate({"intent": "add_tasks", "date": "next_week"})

    with pytest.raises(ValidationError):
        ParsedUserMessage.model_validate(
            {
                "intent": "add_tasks",
                "tasks": [
                    {
                        "title": "задача",
                        "priority": "urgent",
                        "estimated_minutes": 60,
                    }
                ],
            }
        )
