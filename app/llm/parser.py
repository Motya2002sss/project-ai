import json
import re

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.schemas import ParsedTask, ParsedUserMessage


SKIP_PATTERNS = [
    "работаю до",
    "работа до",
    "работаю с",
    "работа с",
    "бюджет",
    "потратить",
    "потрачу",
    "руб",
    "₽",
    "свободен",
    "освобожусь",
]


def _clean_task_title(text: str) -> str:
    text = text.strip(" \n\t.,;:-")

    text = re.sub(
        r"^(сегодня|завтра|послезавтра)?\s*(надо|нужно|хочу|планирую|должен|должна|сделать)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip(" \n\t.,;:-")


def _estimate_minutes(title: str) -> int:
    lowered = title.lower()

    if "собес" in lowered or "подготов" in lowered:
        return 90

    if "зал" in lowered or "трен" in lowered:
        return 60

    if "магаз" in lowered or "продукт" in lowered:
        return 30

    return 60


def _priority(title: str) -> str:
    lowered = title.lower()

    if "собес" in lowered or "карьер" in lowered or "учеб" in lowered:
        return "high"

    return "medium"


def _extract_budget(text: str) -> int | None:
    match = re.search(r"(?:бюджет|потратить|траты|лимит)[^\d]*(\d{2,7})", text, re.IGNORECASE)

    if not match:
        match = re.search(r"(\d{2,7})\s*(?:руб|₽)", text, re.IGNORECASE)

    if not match:
        return None

    return int(match.group(1))


def _extract_work_until(text: str) -> str | None:
    match = re.search(
        r"(?:работаю|работа|свободен|освобожусь)[^\d]*(\d{1,2})(?::(\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def _extract_energy(text: str) -> str | None:
    lowered = text.lower()

    if any(word in lowered for word in ["устал", "мало сил", "нет сил", "разбит", "сонный"]):
        return "low"

    if any(word in lowered for word in ["много сил", "заряжен", "энергии много"]):
        return "high"

    return None


def _extract_date(text: str) -> str | None:
    lowered = text.lower()

    if "завтра" in lowered:
        return "tomorrow"

    if "сегодня" in lowered:
        return "today"

    return None


def _fallback_parse(text: str) -> ParsedUserMessage:
    normalized_text = text.replace("\n", ",")
    raw_parts = re.split(r"[,;]", normalized_text)

    tasks: list[ParsedTask] = []

    for raw_part in raw_parts:
        part = raw_part.strip()

        if not part:
            continue

        lowered = part.lower()

        if any(pattern in lowered for pattern in SKIP_PATTERNS):
            continue

        part = _clean_task_title(part)

        if not part:
            continue

        sub_parts = re.split(r"\s+и\s+", part, flags=re.IGNORECASE)

        for sub_part in sub_parts:
            title = _clean_task_title(sub_part)

            if len(title) < 2:
                continue

            lowered_title = title.lower()

            if any(pattern in lowered_title for pattern in SKIP_PATTERNS):
                continue

            tasks.append(
                ParsedTask(
                    title=title[:255],
                    priority=_priority(title),
                    estimated_minutes=_estimate_minutes(title),
                )
            )

    if not tasks:
        tasks.append(
            ParsedTask(
                title=text.strip()[:255],
                priority="medium",
                estimated_minutes=60,
            )
        )

    return ParsedUserMessage(
        date=_extract_date(text),
        work_until=_extract_work_until(text),
        budget_limit=_extract_budget(text),
        energy_level=_extract_energy(text),
        tasks=tasks,
        raw_text=text,
    )


def _parse_with_llm(text: str) -> ParsedUserMessage:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is empty")

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
    )

    model = settings.llm_model or "gpt-4o-mini"

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("Empty LLM response")

    data = json.loads(content)
    data["raw_text"] = text

    return ParsedUserMessage.model_validate(data)


def parse_user_message(text: str) -> ParsedUserMessage:
    provider = (settings.llm_provider or "mock").lower()

    if provider in {"openai", "custom", "openai-compatible"} and settings.llm_api_key:
        try:
            return _parse_with_llm(text)
        except (RuntimeError, json.JSONDecodeError, ValidationError, Exception):
            return _fallback_parse(text)

    return _fallback_parse(text)
