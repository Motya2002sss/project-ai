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

    def raise_llm_error(text: str):
        raise RuntimeError("simulated llm outage")

    monkeypatch.setattr(parser, "_parse_with_llm", raise_llm_error)

    parsed = parser.parse_user_message("Что сделать для целей?")

    assert parsed.intent == "suggest_goal_tasks"


def test_llm_parser_logs_safe_warning_on_fallback(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def raise_llm_error(text: str):
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
        def __init__(self, api_key, base_url=None, timeout=None):
            assert api_key == "test-key"
            assert base_url == "http://localhost:11434/v1"
            assert timeout == 7
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
    assert "LLMInputTooLongError" in caplog.text


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
