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
    "график",
    "бюджет",
    "потратить",
    "потрачу",
    "руб",
    "₽",
    "свободен",
    "освобожусь",
    "задержался",
    "задержусь",
    "сил мало",
    "мало сил",
    "нет сил",
    "устал",
    "энергия",
    "спать",
    "сон",
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


def _normalize_time(hour: int, minute: int = 0) -> str | None:
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


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

    if "собес" in lowered or "карьер" in lowered or "учеб" in lowered or "подготов" in lowered:
        return "high"

    return "medium"


def _extract_budget(text: str) -> int | None:
    match = re.search(r"(?:бюджет|потратить|траты|лимит)[^\d]*(\d{2,7})", text, re.IGNORECASE)

    if not match:
        match = re.search(r"(\d{2,7})\s*(?:руб|₽)", text, re.IGNORECASE)

    if not match:
        return None

    return int(match.group(1))


def _extract_work_start(text: str) -> str | None:
    match = re.search(
        r"(?:работаю|работа|график)[^\d]*(?:с|от)\s*(\d{1,2})(?::(\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_work_until(text: str) -> str | None:
    # Сначала кейс "с 9 до 18"
    match = re.search(
        r"(?:работаю|работа|график)[^\d]*(?:с|от)\s*\d{1,2}(?::\d{2})?\s*(?:до|-)\s*(\d{1,2})(?::(\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if match:
        return _normalize_time(int(match.group(1)), int(match.group(2) or 0))

    match = re.search(
        r"(?:работаю|работа|свободен|освобожусь|задержался|задержусь)[^\d]*(\d{1,2})(?::(\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_sleep_time(text: str) -> str | None:
    match = re.search(
        r"(?:спать|сон|лечь|ложиться)[^\d]*(\d{1,2})(?::(\d{2}))?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_energy(text: str) -> str | None:
    lowered = text.lower()

    if any(word in lowered for word in ["устал", "мало сил", "сил мало", "нет сил", "разбит", "сонный"]):
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


def _extract_done_task_title(text: str) -> str | None:
    cleaned = text.lower().strip(" .,!?:;")

    words_to_remove = [
        "я",
        "уже",
        "сегодня",
        "задачу",
        "сделал",
        "сделала",
        "сделано",
        "выполнил",
        "выполнила",
        "готово",
        "закрыл",
        "закрыла",
        "отметь",
        "как",
    ]

    for word in words_to_remove:
        cleaned = re.sub(rf"\b{word}\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;")

    return cleaned or None



def _clean_summary_title(value: str) -> str:
    cleaned = value.lower().strip(" .,!?:;")

    words_to_remove = [
        "итог",
        "итоги",
        "дня",
        "за",
        "сегодня",
        "я",
        "уже",
        "задачу",
        "сделал",
        "сделала",
        "сделано",
        "выполнил",
        "выполнила",
        "готово",
        "закрыл",
        "закрыла",
        "купил",
        "купила",
        "сходил",
        "сходила",
        "прочитал",
        "прочитала",
        "не сделал",
        "не сделала",
        "не успел",
        "не успела",
        "не выполнил",
        "не выполнила",
        "пропустил",
        "пропустила",
    ]

    for phrase in sorted(words_to_remove, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.replace(":", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;")

    return cleaned


def _extract_summary_titles(text: str) -> tuple[list[str], list[str]]:
    done_titles: list[str] = []
    skipped_titles: list[str] = []

    chunks = re.split(r"[,;\n]", text)

    for chunk in chunks:
        chunk = chunk.strip()

        if not chunk:
            continue

        lowered = chunk.lower()

        is_skipped = any(
            phrase in lowered
            for phrase in [
                "не сделал",
                "не сделала",
                "не успел",
                "не успела",
                "не выполнил",
                "не выполнила",
                "пропустил",
                "пропустила",
            ]
        )

        is_done = any(
            phrase in lowered
            for phrase in [
                "сделал",
                "сделала",
                "выполнил",
                "выполнила",
                "готово",
                "закрыл",
                "закрыла",
                "купил",
                "купила",
                "сходил",
                "сходила",
                "прочитал",
                "прочитала",
            ]
        )

        title = _clean_summary_title(chunk)

        if not title:
            continue

        if is_skipped:
            skipped_titles.append(title)
        elif is_done:
            done_titles.append(title)

    return done_titles, skipped_titles



def _detect_intent(text: str) -> str:
    lowered = text.lower().strip()

    if lowered.startswith("/plan"):
        return "show_plan"

    if lowered.startswith("/tasks"):
        return "show_tasks"

    if lowered.startswith("/clear"):
        return "clear_tasks"

    if lowered.startswith("/done"):
        return "mark_done"

    if any(phrase in lowered for phrase in [
        "мой профиль",
        "покажи профиль",
        "что ты обо мне знаешь",
    ]):
        return "show_profile"

    if any(phrase in lowered for phrase in [
        "мой график",
        "обычно работаю",
        "работаю с",
        "работа с",
        "график с",
        "хочу спать",
        "ложиться в",
        "спать в",
        "сон в",
    ]):
        return "update_profile"

    if any(phrase in lowered for phrase in [
        "покажи план",
        "что по плану",
        "расписание",
        "мой план",
        "какой план",
        "план на день",
    ]):
        return "show_plan"

    if any(phrase in lowered for phrase in [
        "покажи задачи",
        "список задач",
        "мои задачи",
        "что по задачам",
        "какие задачи",
    ]):
        return "show_tasks"

    if any(phrase in lowered for phrase in [
        "очисти задачи",
        "очистить задачи",
        "почисти задачи",
        "удали задачи",
        "удалить задачи",
        "удали все задачи",
        "сбрось задачи",
        "сбросить задачи",
        "очисти всё",
        "очистить всё",
    ]):
        return "clear_tasks"

    if any(phrase in lowered for phrase in [
        "итог дня",
        "итоги дня",
        "отчет дня",
        "отчёт дня",
        "подведи итог",
        "что сделал за день",
    ]):
        return "daily_summary"

    if "," in lowered and any(word in lowered for word in [
        "сделал",
        "сделала",
        "выполнил",
        "выполнила",
        "не сделал",
        "не успел",
        "готово",
    ]):
        return "daily_summary"

    if any(word in lowered for word in [
        "сделал",
        "сделала",
        "сделано",
        "выполнил",
        "выполнила",
        "готово",
        "закрыл",
        "закрыла",
    ]):
        return "mark_done"

    if any(word in lowered for word in ["задержался", "задержусь", "освобожусь", "работаю до"]):
        if not any(word in lowered for word in ["хочу", "надо", "нужно", "планирую"]):
            return "reschedule"

    return "add_tasks"


def _fallback_extract_tasks(text: str) -> list[ParsedTask]:
    normalized_text = text.replace("\n", ",")
    raw_parts = re.split(r"[,;]", normalized_text)

    tasks: list[ParsedTask] = []

    for raw_part in raw_parts:
        part = raw_part.strip()

        if not part:
            continue

        lowered = part.lower()

        if lowered.startswith("/"):
            continue

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

            if lowered_title.startswith("/"):
                continue

            if any(pattern in lowered_title for pattern in SKIP_PATTERNS):
                continue

            tasks.append(
                ParsedTask(
                    title=title[:255],
                    priority=_priority(title),
                    estimated_minutes=_estimate_minutes(title),
                )
            )

    return tasks


def _fallback_parse(text: str) -> ParsedUserMessage:
    intent = _detect_intent(text)

    tasks: list[ParsedTask] = []

    if intent == "add_tasks":
        tasks = _fallback_extract_tasks(text)

        if not tasks:
            tasks.append(
                ParsedTask(
                    title=text.strip()[:255],
                    priority="medium",
                    estimated_minutes=60,
                )
            )

    done_task_titles, skipped_task_titles = (
        _extract_summary_titles(text)
        if intent == "daily_summary"
        else ([], [])
    )

    return ParsedUserMessage(
        intent=intent,
        date=_extract_date(text),
        work_start=_extract_work_start(text),
        work_until=_extract_work_until(text),
        sleep_time=_extract_sleep_time(text),
        budget_limit=_extract_budget(text),
        energy_level=_extract_energy(text),
        done_task_title=_extract_done_task_title(text) if intent == "mark_done" else None,
        done_task_titles=done_task_titles,
        skipped_task_titles=skipped_task_titles,
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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
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
