import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.llm import parser
from app.llm.schemas import ParsedUserMessage


def test_mock_parser_works_without_llm_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    parsed = parser.parse_user_message("Завтра хочу позаниматься математикой")

    assert parsed.intent == "add_tasks"
    assert parsed.date == "tomorrow"
    assert parsed.tasks
    assert parsed.tasks[0].title == "позаниматься математикой"


def test_llm_parser_falls_back_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def raise_llm_error(text: str):
        raise RuntimeError("simulated llm outage")

    monkeypatch.setattr(parser, "_parse_with_llm", raise_llm_error)

    parsed = parser.parse_user_message("Что сделать для целей?")

    assert parsed.intent == "suggest_goal_tasks"


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
