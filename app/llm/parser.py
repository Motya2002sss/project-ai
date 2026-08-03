import json
import logging
import re
from typing import get_args

import httpx
from openai import OpenAI

from app.core.config import settings
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.schemas import Intent, ParsedTask, ParsedUserMessage


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
        r"^(?:(?:пожалуйста|мне)\s+)*(?:добавь|добавить|создай|создать|запиши|записать|"
        r"поставь|поставить|напомни|напомнить)\s+(?:мне\s+)?(?:(?:задачу|дело)\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )

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


def _extract_task_time(text: str) -> str | None:
    match = re.search(r"\b(?:в|на|с)\s*(\d{1,2})(?::(\d{2}))?\b", text, re.IGNORECASE)

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_fixed_end(text: str) -> str | None:
    match = re.search(
        r"\b(?:с|в)\s*\d{1,2}(?::\d{2})?\s*(?:до|[-–—])\s*(\d{1,2})(?::(\d{2}))\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_duration_minutes(text: str) -> int | None:
    lowered = text.lower().replace("ё", "е")

    minute_match = re.search(r"\b(\d{1,4})\s*(?:мин(?:ут[уы]?)?|минутку)\b", lowered)

    if minute_match:
        return min(int(minute_match.group(1)), 1440)

    hour_match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:ч(?:ас(?:а|ов)?)?)\b", lowered)

    if hour_match:
        hours = float(hour_match.group(1).replace(",", "."))
        return min(max(int(hours * 60), 1), 1440)

    if "полтора часа" in lowered or "полтора часа" in lowered:
        return 90

    if "полчаса" in lowered or "пол часа" in lowered:
        return 30

    if re.search(r"\bна\s+(?:один\s+)?час\b", lowered):
        return 60

    return None


def _extract_preferred_window(text: str) -> str | None:
    lowered = text.lower()

    if re.search(r"\b(утром|утро|с утра)\b", lowered):
        return "morning"

    if re.search(r"\b(днем|днём|после обеда)\b", lowered):
        return "afternoon"

    if re.search(r"\b(вечером|вечер)\b", lowered):
        return "evening"

    return None


def _extract_earliest_start(text: str) -> str | None:
    match = re.search(
        r"\b(?:после|не раньше)\s*(\d{1,2})(?::(\d{2}))\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _extract_latest_end(text: str) -> str | None:
    match = re.search(
        r"\b(?:закончить\s+до|не позже|до)\s*(\d{1,2})(?::(\d{2}))\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return _normalize_time(int(match.group(1)), int(match.group(2) or 0))


def _clean_scheduled_task_title(text: str) -> str:
    cleaned = text.strip(" \n\t.,;:-")
    cleaned = re.sub(r"\b(?:сегодня|завтра|на сегодня|на завтра)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:утром|днем|днём|вечером|с утра|после обеда)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:после|не раньше)\s*\d{1,2}(?::\d{2})\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:закончить\s+до|не позже|до)\s*\d{1,2}(?::\d{2})\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:в|на)\s*\d{1,2}(?::\d{2})?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:с|в)\s*\d{1,2}(?::\d{2})?\s*(?:до|[-–—])\s*\d{1,2}(?::\d{2})\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,4}\s*(?:мин(?:ут[уы]?)?|ч(?:ас(?:а|ов)?)?)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:на\s+)?(?:полтора часа|полчаса|пол часа|один час|час)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    cleaned = re.sub(
        r"^(?:я\s+)?(?:надо|нужно|хочу|планирую|добавь|добавить|запиши|записать)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \n\t.,;:-")

    return cleaned


def _clean_operation_reference(text: str, operation: str) -> str:
    cleaned = text.strip(" \n\t.,;:-")

    if operation == "cancel":
        cleaned = re.sub(r"\b(?:отмени(?:ть)?|отменяется|отменить|отмена)\b", " ", cleaned, flags=re.IGNORECASE)
    elif operation == "update":
        cleaned = re.sub(r"\b(?:перенеси(?:ть)?|переносится|перенести)\b", " ", cleaned, flags=re.IGNORECASE)
    elif operation == "complete":
        cleaned = _extract_done_task_title(cleaned) or ""

    cleaned = re.sub(r"\b(?:сегодня|завтра|на сегодня|на завтра)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \n\t.,;:-")

    return cleaned


def _is_capability_request_text(text: str) -> bool:
    lowered = text.lower().replace("ё", "е")
    return bool(
        re.search(r"\b(?:сделай|создай|добавь|хочу|нужен|нужна)\b", lowered)
        and re.search(
            r"\b(?:отдельн\w*\s+)?(?:трекер|счетчик|раздел|экран|интеграц\w*|функци\w*)\b",
            lowered,
        )
        and not re.search(r"\b(?:задач\w*|разов\w*)\b", lowered)
    )


def _is_context_only_message(text: str, energy_level: str | None) -> bool:
    lowered = text.lower().replace("ё", "е")
    asks_to_reduce = any(
        phrase in lowered
        for phrase in [
            "оставь только главное",
            "оставить только главное",
            "оставь только важное",
            "оставить только важное",
            "убери лишнее",
        ]
    )
    has_task_action = bool(
        re.search(
            r"\b(?:добавь|добавить|хочу|надо|нужно|планирую|сделать|позвонить|купить|"
            r"подготовить|оплатить|сходить|почитать|перенеси|отмени)\b",
            lowered,
        )
    )

    return bool((asks_to_reduce or energy_level) and not has_task_action)


def _fallback_semantic_task(text: str, intent: str) -> ParsedTask | None:
    lowered = text.lower().replace("ё", "е")
    target_date = _extract_date(text)
    explicit_start = _extract_task_time(text)
    explicit_end = _extract_fixed_end(text)
    duration = _extract_duration_minutes(text)
    preferred_window = _extract_preferred_window(text)
    earliest_start = _extract_earliest_start(text)
    latest_end = _extract_latest_end(text)

    ambiguous_tracking = bool(
        re.search(r"\b(?:считать|считал\w*|отслеживать|учет|записывать|фиксировать)\b", lowered)
        and re.search(r"\b(?:добавь|добавить|сделай|создай|хочу)\b", lowered)
        and not re.search(
            r"\b(?:задач\w*|разов\w*|кажд\w*\s+день|ежеднев\w*|по будням|регуляр\w*)\b",
            lowered,
        )
    )

    if ambiguous_tracking:
        subject = re.split(
            r"\b(?:чтобы|для того чтобы|считать|считал\w*|отслеживать|учет|записывать|фиксировать)\b",
            _clean_task_title(text),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,!?:;-")
        return ParsedTask(
            title=subject or "Уточнить формат отслеживания",
            operation="create",
            scheduling_type="unscheduled",
            target_date=target_date,
            needs_clarification=True,
            clarification_reason="ambiguous_entity_kind",
        )

    if re.search(r"\b(?:отменяется|отмени(?:ть)?|отменить)\b", lowered):
        reference = _clean_operation_reference(text, "cancel")
        return ParsedTask(
            title=reference or "Отменить задачу",
            operation="cancel",
            target_date=target_date,
            referenced_task_title=reference or None,
        )

    if re.search(r"\b(?:перенеси(?:ть)?|переносится|перенести)\b", lowered):
        reference = _clean_operation_reference(text, "update")
        return ParsedTask(
            title=reference or "Перенести задачу",
            operation="update",
            target_date=target_date,
            referenced_task_title=reference or None,
        )

    duration_delta_match = re.search(
        r"\bдобавь\s+(?:еще|ещё)?\s*(\d{1,4})\s*мин(?:ут[уы]?)?\s+(?:на|к)\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if duration_delta_match:
        reference = duration_delta_match.group(2).strip(" .,!?:;")
        return ParsedTask(
            title=reference,
            operation="update",
            target_date=target_date,
            duration_delta_minutes=int(duration_delta_match.group(1)),
            referenced_task_title=reference,
        )

    if intent == "mark_done":
        reference = _clean_operation_reference(text, "complete")
        return ParsedTask(
            title=reference or "Выполненная задача",
            operation="complete",
            target_date=target_date,
            referenced_task_title=reference or None,
        )

    recurrence_match = re.search(
        r"\b(?:обычно|кажд\w*\s+день|ежеднев\w*|по будням|регуляр\w*|напоминай\w*|хожу)\b",
        lowered,
    )

    if recurrence_match:
        title = _clean_scheduled_task_title(text)
        explicit_recurrence = bool(
            re.search(
                r"\b(?:кажд\w*\s+день|ежеднев\w*|по будням|регуляр\w*|напоминай\w*)\b",
                lowered,
            )
        )
        title = re.sub(
            r"^(?:кажд\w*\s+день|ежеднев\w*|по будням|регуляр\w*)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"^напоминай\w*\s+(?:мне\s+)?", "", title, flags=re.IGNORECASE)
        needs_clarification = not explicit_recurrence or not (preferred_window or explicit_start)
        return ParsedTask(
            title=title or text.strip()[:255],
            operation="create",
            scheduling_type="unscheduled",
            target_date=target_date,
            preferred_window=preferred_window,
            recurrence_hint=recurrence_match.group(0),
            needs_clarification=needs_clarification,
            clarification_reason=(
                "missing_routine_time"
                if explicit_recurrence and needs_clarification
                else "ambiguous_recurrence"
                if needs_clarification
                else None
            ),
        )

    confirmed_event = re.search(r"\b(?:записался|записалась|договорился|договорилась)\b", lowered)

    if confirmed_event:
        title = re.sub(
            r"^(?:я\s+)?(?:записался|записалась|договорился|договорилась)\s+(?:на\s+)?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        title = _clean_scheduled_task_title(title)

        if not explicit_start:
            return ParsedTask(
                title=title or text.strip()[:255],
                operation="create",
                scheduling_type="unscheduled",
                target_date=target_date,
                estimated_minutes=duration,
                needs_clarification=True,
                clarification_reason="missing_fixed_time",
            )

        return ParsedTask(
            title=title or text.strip()[:255],
            operation="create",
            scheduling_type="fixed",
            target_date=target_date,
            fixed_start=explicit_start,
            fixed_end=explicit_end,
            estimated_minutes=duration or 60,
        )

    if explicit_start and intent == "add_tasks":
        title = _clean_scheduled_task_title(text)
        return ParsedTask(
            title=title or text.strip()[:255],
            operation="create",
            scheduling_type="fixed",
            target_date=target_date,
            fixed_start=explicit_start,
            fixed_end=explicit_end,
            estimated_minutes=duration or 60,
            priority=_priority(title),
        )

    if intent == "add_tasks" and (preferred_window or earliest_start or latest_end):
        title = _clean_scheduled_task_title(text)
        return ParsedTask(
            title=title or text.strip()[:255],
            operation="create",
            scheduling_type="flexible",
            target_date=target_date,
            preferred_window=preferred_window,
            earliest_start=earliest_start,
            latest_end=latest_end,
            estimated_minutes=duration or _estimate_minutes(title),
            priority=_priority(title),
        )

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
        "закончил",
        "закончила",
        "оплатил",
        "оплатила",
        "купил",
        "купила",
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
        "закончил",
        "закончила",
        "оплатил",
        "оплатила",
        "купил",
        "купила",
    ]):
        return "mark_done"

    if any(word in lowered for word in ["задержался", "задержусь", "освобожусь", "работаю до"]):
        if not any(word in lowered for word in ["хочу", "надо", "нужно", "планирую"]):
            return "reschedule"

    return "add_tasks"


def _fallback_extract_tasks(text: str) -> list[ParsedTask]:
    normalized_text = text.replace("\n", ",")
    raw_parts = re.split(r"[,;]", normalized_text)
    target_date = _extract_date(text)

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

        duration = _extract_duration_minutes(part)
        part = _clean_scheduled_task_title(part) if duration else _clean_task_title(part)

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
                    target_date=target_date,
                    priority=_priority(title),
                    estimated_minutes=duration or _estimate_minutes(title),
                )
            )

    return tasks


def _fallback_semantic_tasks(text: str) -> list[ParsedTask]:
    parts = [part.strip() for part in re.split(r"[,;\n]", text) if part.strip()]

    if len(parts) < 2:
        return []

    candidates = [_fallback_semantic_task(part, "add_tasks") for part in parts]
    tasks = [candidate for candidate in candidates if candidate is not None]

    return tasks if len(tasks) >= 2 else []


def _fallback_parse(text: str) -> ParsedUserMessage:
    intent = _detect_intent(text)

    tasks: list[ParsedTask] = []
    goals: list[str] = []
    budget_limit = None if intent == "update_goals" else _extract_budget(text)

    energy_level = _extract_energy(text)
    capability_request = _is_capability_request_text(text)
    context_only = _is_context_only_message(text, energy_level)
    semantic_tasks: list[ParsedTask] = []

    if intent in {"add_tasks", "mark_done", "reschedule"} and not capability_request and not context_only:
        semantic_tasks = _fallback_semantic_tasks(text)

        if not semantic_tasks:
            semantic_task = _fallback_semantic_task(text, intent)

            if semantic_task:
                semantic_tasks = [semantic_task]

    if semantic_tasks:
        tasks = semantic_tasks
    elif intent == "add_tasks" and not capability_request and not context_only:
        tasks = _fallback_extract_tasks(text)

        if not tasks:
            tasks.append(
                ParsedTask(
                    title=text.strip()[:255],
                    target_date=_extract_date(text),
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
    parsed_date = _extract_date(text)

    if len(semantic_tasks) > 1:
        task_dates = {task.target_date for task in semantic_tasks}

        if None in task_dates and len(task_dates) > 1:
            parsed_date = None

    return ParsedUserMessage(
        intent=intent,
        date=parsed_date,
        work_start=_extract_work_start(text),
        work_until=_extract_work_until(text),
        sleep_time=_extract_sleep_time(text),
        budget_limit=budget_limit,
        energy_level=energy_level,
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

    normalized_tasks = []

    for task in normalized["tasks"]:
        if not isinstance(task, dict):
            normalized_tasks.append(task)
            continue

        normalized_task = dict(task)

        for field in [
            "operation",
            "scheduling_type",
            "target_date",
            "fixed_start",
            "fixed_end",
            "preferred_window",
            "earliest_start",
            "latest_end",
            "deadline",
            "estimated_minutes",
            "duration_delta_minutes",
            "referenced_task_title",
            "recurrence_hint",
            "clarification_reason",
        ]:
            if field in normalized_task:
                normalized_task[field] = _normalize_empty_llm_value(normalized_task[field])

        if normalized_task.get("operation") is None:
            normalized_task["operation"] = "create"

        for field in ["fixed_start", "fixed_end", "earliest_start", "latest_end"]:
            if field in normalized_task:
                normalized_task[field] = _normalize_llm_time(normalized_task[field])

        if normalized_task.get("operation") == "unscheduled":
            normalized_task["operation"] = "create"
            normalized_task["scheduling_type"] = "unscheduled"

        normalized_tasks.append(normalized_task)

    normalized["tasks"] = normalized_tasks

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

    if isinstance(data, dict) and data.get("intent") not in get_args(Intent):
        data["intent"] = _detect_intent(text)

    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        fallback_intent = _detect_intent(text)
        fallback_task = _fallback_semantic_task(text, fallback_intent)

        if fallback_task is None:
            fallback_tasks = _fallback_extract_tasks(text) if fallback_intent == "add_tasks" else []
            fallback_task = fallback_tasks[0] if fallback_tasks else None

        if fallback_task:
            for task_data in data["tasks"]:
                if isinstance(task_data, dict) and not str(task_data.get("title") or "").strip():
                    task_data["title"] = fallback_task.title

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
    capability_request = _is_capability_request_text(text)
    context_only = _is_context_only_message(text, parsed.energy_level or _extract_energy(text))
    semantic_tasks = (
        _fallback_semantic_tasks(text)
        if fallback_intent in {"add_tasks", "mark_done", "reschedule"}
        else []
    )

    if capability_request or context_only:
        parsed.intent = "add_tasks"
        parsed.tasks = []

    if semantic_tasks:
        parsed.intent = "add_tasks"
        parsed.tasks = semantic_tasks

        task_dates = {task.target_date for task in semantic_tasks}
        parsed.date = None if None in task_dates and len(task_dates) > 1 else text_date

    if fallback_intent == "suggest_goal_tasks":
        parsed.intent = "suggest_goal_tasks"

    if fallback_intent == "reschedule":
        parsed.intent = "reschedule"

    if fallback_intent == "update_profile" and parsed.intent == "add_tasks":
        parsed.intent = "update_profile"
        parsed.tasks = []

    if not semantic_tasks:
        parsed.date = text_date
    parsed.work_start = parsed.work_start or _extract_work_start(text)
    parsed.work_until = parsed.work_until or _extract_work_until(text)
    parsed.sleep_time = parsed.sleep_time or _extract_sleep_time(text)

    if parsed.energy_level is None:
        parsed.energy_level = _extract_energy(text)

    parsed.budget_limit = _extract_budget(text)

    semantic_task = None if semantic_tasks or capability_request or context_only else _fallback_semantic_task(
        text,
        fallback_intent,
    )

    if semantic_task and fallback_intent in {"add_tasks", "mark_done", "reschedule"}:
        if (
            semantic_task.operation != "create"
            or semantic_task.needs_clarification
            or semantic_task.recurrence_hint
        ):
            parsed.intent = fallback_intent

        if not parsed.tasks:
            parsed.tasks = [semantic_task]
        elif (
            semantic_task.operation != "create"
            or semantic_task.needs_clarification
            or semantic_task.scheduling_type == "fixed"
            or semantic_task.preferred_window
            or semantic_task.earliest_start
            or semantic_task.latest_end
        ):
            parsed_task = parsed.tasks[0]
            parsed_task.title = semantic_task.title
            parsed_task.operation = semantic_task.operation
            parsed_task.scheduling_type = semantic_task.scheduling_type
            parsed_task.target_date = semantic_task.target_date
            parsed_task.fixed_start = semantic_task.fixed_start or parsed_task.fixed_start
            parsed_task.fixed_end = semantic_task.fixed_end or parsed_task.fixed_end
            parsed_task.preferred_window = semantic_task.preferred_window or parsed_task.preferred_window
            parsed_task.earliest_start = semantic_task.earliest_start or parsed_task.earliest_start
            parsed_task.latest_end = semantic_task.latest_end or parsed_task.latest_end
            parsed_task.estimated_minutes = semantic_task.estimated_minutes or parsed_task.estimated_minutes
            parsed_task.duration_delta_minutes = (
                semantic_task.duration_delta_minutes or parsed_task.duration_delta_minutes
            )
            parsed_task.referenced_task_title = (
                semantic_task.referenced_task_title or parsed_task.referenced_task_title
            )
            parsed_task.recurrence_hint = semantic_task.recurrence_hint or parsed_task.recurrence_hint
            parsed_task.needs_clarification = semantic_task.needs_clarification
            parsed_task.clarification_reason = (
                semantic_task.clarification_reason or parsed_task.clarification_reason
            )

            if semantic_task.scheduling_type == "flexible" and (
                semantic_task.preferred_window
                or semantic_task.earliest_start
                or semantic_task.latest_end
            ):
                parsed_task.fixed_start = None
                parsed_task.fixed_end = None

    if (
        fallback_intent == "add_tasks"
        and not parsed.tasks
        and not capability_request
        and not context_only
    ):
        parsed.intent = "add_tasks"
        parsed.tasks = _fallback_extract_tasks(text)

    if (
        fallback_intent == "add_tasks"
        and semantic_task is None
        and parsed.tasks
        and not semantic_tasks
    ):
        fallback_tasks = _fallback_extract_tasks(text)
        explicit_duration = _extract_duration_minutes(text)

        for parsed_task, fallback_task in zip(parsed.tasks, fallback_tasks):
            if parsed_task.operation != "create":
                continue

            parsed_task.target_date = text_date

            if parsed_task.estimated_minutes is None:
                parsed_task.estimated_minutes = fallback_task.estimated_minutes

            if parsed_task.scheduling_type == "unscheduled" and not parsed_task.needs_clarification:
                parsed_task.scheduling_type = fallback_task.scheduling_type

            if (
                explicit_duration
                and fallback_task.scheduling_type == "flexible"
                and not parsed_task.fixed_start
                and not parsed_task.recurrence_hint
            ):
                parsed_task.scheduling_type = "flexible"
                parsed_task.needs_clarification = False
                parsed_task.clarification_reason = None

    if parsed.intent != "update_goals":
        parsed.goals = []

    for task in parsed.tasks:
        if task.target_date is None:
            task.target_date = text_date

        if task.fixed_start:
            task.scheduling_type = "fixed"

        if task.operation == "complete" and parsed.done_task_title is None:
            parsed.done_task_title = task.referenced_task_title or task.title

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


def _effective_llm_timeout() -> float:
    request_budget = max(settings.message_request_timeout_seconds - 2.0, 1.0)
    return max(min(settings.llm_timeout_seconds, request_budget), 1.0)


def _parse_with_openai_compatible(text: str) -> ParsedUserMessage:
    if not settings.llm_api_key:
        raise RuntimeError("LLM API key is not configured")

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        timeout=_effective_llm_timeout(),
        max_retries=0,
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
            "temperature": 0,
        },
    }

    timeout_seconds = _effective_llm_timeout()
    timeout = httpx.Timeout(timeout_seconds, connect=min(3.0, timeout_seconds))

    with httpx.Client(timeout=timeout) as client:
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
