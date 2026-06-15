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
            assert timeout == 11

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
