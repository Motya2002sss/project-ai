import json
import logging
import re

import httpx
from openai import OpenAI

from app.core.config import settings
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.schemas import ParsedTask, ParsedUserMessage


LLM_PROVIDERS = {"openai", "openai-compatible", "custom", "ollama"}
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
MAX_LOG_MESSAGE_CHARS = 300

logger = logging.getLogger(__name__)


class LLMInputTooLongError(ValueError):
    pass


def _with_parser_metadata(
    parsed: ParsedUserMessage,
    *,
    parser_provider: str,
    used_fallback: bool = False,
    fallback_reason: str | None = None,
) -> ParsedUserMessage:
    parsed.parser_provider = parser_provider
    parsed.used_fallback = used_fallback
    parsed.fallback_reason = fallback_reason

    return parsed


def _sanitize_error_message(error: Exception) -> str:
    message = str(error) or error.__class__.__name__

    sensitive_values = [
        settings.llm_api_key,
        settings.telegram_bot_token,
        settings.database_url,
        settings.postgres_password,
    ]

    for value in sensitive_values:
        if value:
            message = message.replace(value, "[redacted]")

    message = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+", r"\1[redacted]", message)
    message = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)\S+", r"\1[redacted]", message)
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-[redacted]", message)
    message = re.sub(
        r"postgresql(?:\+psycopg)?://[^\s]+",
        "postgresql://[redacted]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(r"\s+", " ", message).strip()

    return message[:MAX_LOG_MESSAGE_CHARS]


def _log_llm_fallback(error: Exception, provider: str) -> None:
    logger.warning(
        "LLM parser fallback to mock: provider=%s model=%s error_class=%s error=%s",
        provider,
        settings.llm_model or DEFAULT_LLM_MODEL,
        error.__class__.__name__,
        _sanitize_error_message(error),
    )


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


def _normalize_time(hour: int, minute: int = 0) -> str | None:
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def _clean_task_title(text: str) -> str:
    text = text.strip(" \n\t.,;:-")

    text = re.sub(
        r"^(но\s+)?(сегодня|завтра|послезавтра)?\s*(надо|нужно|хочу|планирую|должен|должна|сделать)\s+",
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

    if any(
        word in lowered
        for word in [
            "собес",
            "карьер",
            "учеб",
            "подготов",
            "экзамен",
            "дедлайн",
            "сроч",
        ]
    ):
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


def _clean_goal_title(text: str) -> str:
    cleaned = text.strip(" \n\t.,;:-")

    cleaned = re.sub(
        r"^(моя|мои|главная|основная)?\s*(цель|цели)\s*[:\-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^(хочу|надо|нужно|планирую)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip(" \n\t.,;:-")


def _extract_goals(text: str) -> list[str]:
    lowered = text.lower()

    if "цель" not in lowered and "цели" not in lowered:
        return []

    cleaned = re.sub(
        r"^(мои\s+цели|моя\s+цель|цели|цель)\s*[:\-]?\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )

    parts = re.split(r"[,;\n]|\s+и\s+", cleaned)

    goals: list[str] = []

    for part in parts:
        title = _clean_goal_title(part)

        if len(title) >= 3:
            goals.append(title[:255])

    return goals


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

    if (
        re.search(r"что\s+(?:сегодня|завтра)?\s*сделать\s+(?:для|по)\s+цел", lowered)
        or any(phrase in lowered for phrase in [
            "задачи для целей",
            "задачи по целям",
            "что делать для целей",
            "что делать по целям",
            "как продвинуться по целям",
        ])
    ):
        return "suggest_goal_tasks"

    if (
        re.search(r"^мои\s+цели\s*[:\-]", lowered)
        or any(phrase in lowered for phrase in [
            "моя цель",
            "цель:",
            "цели:",
            "долгосрочная цель",
        ])
    ):
        return "update_goals"

    if any(phrase in lowered for phrase in [
        "покажи цели",
        "мои цели",
        "список целей",
        "что по целям",
    ]):
        return "show_goals"

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
    goals: list[str] = []
    budget_limit = None if intent == "update_goals" else _extract_budget(text)

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

    if intent == "update_goals":
        goals = _extract_goals(text)

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
        budget_limit=budget_limit,
        energy_level=_extract_energy(text),
        done_task_title=_extract_done_task_title(text) if intent == "mark_done" else None,
        done_task_titles=done_task_titles,
        skipped_task_titles=skipped_task_titles,
        goals=goals,
        tasks=tasks,
        raw_text=text,
    )


def _validate_llm_input(text: str) -> None:
    if len(text) > settings.llm_max_input_chars:
        raise LLMInputTooLongError(
            f"input length {len(text)} exceeds LLM_MAX_INPUT_CHARS={settings.llm_max_input_chars}"
        )


def _normalize_llm_time(value):
    if value is None:
        return None

    if isinstance(value, int):
        return _normalize_time(value)

    if isinstance(value, str):
        value = value.strip()

        if re.fullmatch(r"\d{1,2}", value):
            return _normalize_time(int(value))

        match = re.fullmatch(r"(\d{1,2}):(\d{1,2})", value)

        if match:
            return _normalize_time(int(match.group(1)), int(match.group(2)))

    return value


def _normalize_empty_llm_value(value):
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
        return None

    return value


def _normalize_llm_data(data):
    if not isinstance(data, dict):
        return data

    normalized = dict(data)

    for field in [
        "date",
        "work_start",
        "work_until",
        "sleep_time",
        "energy_level",
        "done_task_title",
        "budget_limit",
    ]:
        if field in normalized:
            normalized[field] = _normalize_empty_llm_value(normalized[field])

    for field in ["work_start", "work_until", "sleep_time"]:
        if field in normalized:
            normalized[field] = _normalize_llm_time(normalized[field])

    for field in ["tasks", "goals", "done_task_titles", "skipped_task_titles"]:
        normalized[field] = _normalize_empty_llm_value(normalized.get(field))

        if normalized[field] is None:
            normalized[field] = []

    return normalized


def _load_llm_json(content: str):
    text = content.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end > start:
            return json.loads(text[start : end + 1])

        raise


def _parse_llm_content(content: str | None, text: str) -> ParsedUserMessage:
    if not content:
        raise RuntimeError("Empty LLM response")

    data = _normalize_llm_data(_load_llm_json(content))
    data["raw_text"] = text

    return _polish_llm_parsed_message(ParsedUserMessage.model_validate(data), text)


def _merge_titles(existing: list[str], extracted: list[str]) -> list[str]:
    merged = list(existing)
    seen = {title.lower().replace("ё", "е") for title in merged}

    for title in extracted:
        key = title.lower().replace("ё", "е")

        if key not in seen:
            merged.append(title)
            seen.add(key)

    return merged


def _polish_llm_parsed_message(parsed: ParsedUserMessage, text: str) -> ParsedUserMessage:
    fallback_intent = _detect_intent(text)
    text_date = _extract_date(text)

    if fallback_intent == "suggest_goal_tasks":
        parsed.intent = "suggest_goal_tasks"

    if fallback_intent == "reschedule":
        parsed.intent = "reschedule"

    if fallback_intent == "update_profile" and parsed.intent == "add_tasks":
        parsed.intent = "update_profile"
        parsed.tasks = []

    parsed.date = text_date

    if parsed.energy_level is None:
        parsed.energy_level = _extract_energy(text)

    parsed.budget_limit = _extract_budget(text)

    if parsed.intent == "daily_summary":
        done_titles, skipped_titles = _extract_summary_titles(text)
        parsed.done_task_titles = _merge_titles(parsed.done_task_titles, done_titles)
        parsed.skipped_task_titles = _merge_titles(parsed.skipped_task_titles, skipped_titles)

    for task in parsed.tasks:
        if task.priority != "high" and _priority(task.title) == "high":
            task.priority = "high"

    return parsed


def _llm_messages(text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]


def _parse_with_openai_compatible(text: str) -> ParsedUserMessage:
    if not settings.llm_api_key:
        raise RuntimeError("LLM API key is not configured")

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        timeout=settings.llm_timeout_seconds,
    )

    model = settings.llm_model or DEFAULT_LLM_MODEL

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=settings.llm_max_output_tokens,
        response_format={"type": "json_object"},
        messages=_llm_messages(text),
    )

    content = response.choices[0].message.content

    return _parse_llm_content(content, text)


def _parse_with_ollama(text: str) -> ParsedUserMessage:
    base_url = (settings.llm_base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = settings.llm_model or "qwen3.5:4b"
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "think": settings.llm_ollama_think,
        "stream": False,
        "messages": _llm_messages(text),
        "options": {
            "num_predict": settings.llm_max_output_tokens,
        },
    }

    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data.get("message", {}).get("content")

    return _parse_llm_content(content, text)


def _parse_with_llm(text: str, provider: str) -> ParsedUserMessage:
    _validate_llm_input(text)

    if provider == "ollama":
        return _parse_with_ollama(text)

    return _parse_with_openai_compatible(text)


def parse_user_message(text: str) -> ParsedUserMessage:
    provider = (settings.llm_provider or "mock").lower()

    if not settings.llm_enabled or provider == "mock":
        return _with_parser_metadata(_fallback_parse(text), parser_provider="mock")

    if provider not in LLM_PROVIDERS:
        error = RuntimeError("Unsupported LLM provider")
        _log_llm_fallback(error, provider=provider)
        return _with_parser_metadata(
            _fallback_parse(text),
            parser_provider="mock",
            used_fallback=True,
            fallback_reason=error.__class__.__name__,
        )

    if provider in LLM_PROVIDERS:
        try:
            return _with_parser_metadata(
                _parse_with_llm(text, provider=provider),
                parser_provider=provider,
            )
        except Exception as error:
            _log_llm_fallback(error, provider=provider)
            return _with_parser_metadata(
                _fallback_parse(text),
                parser_provider="mock",
                used_fallback=True,
                fallback_reason=error.__class__.__name__,
            )

    return _with_parser_metadata(_fallback_parse(text), parser_provider="mock")
