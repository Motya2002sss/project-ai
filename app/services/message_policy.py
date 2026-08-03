import re
from dataclasses import dataclass

from app.llm.schemas import ParsedTask, ParsedUserMessage


COMMAND_PREFIX_RE = re.compile(
    r"^(?:(?:пожалуйста|мне)\s+)*(?:добавь|добавить|создай|создать|запиши|записать|"
    r"поставь|поставить|напомни|напомнить)\s+(?:(?:мне\s+)?(?:задачу|дело)\s+)?",
    re.IGNORECASE,
)
REPLAN_SUFFIX_RE = re.compile(
    r"\s+и\s+(?:оставь|оставить|сохрани|сохранить)\s+(?:только\s+)?(?:главное|важное).*$",
    re.IGNORECASE,
)
CAPABILITY_RE = re.compile(
    r"\b(?:отдельн\w*\s+)?(?:трекер|сч[её]тчик|раздел|экран|интеграц\w*|функци\w*)\b",
    re.IGNORECASE,
)
TRACKING_RE = re.compile(
    r"\b(?:считать|считал\w*|отслеживать|уч[её]т|записывать|фиксировать)\b",
    re.IGNORECASE,
)
EXPLICIT_TASK_RE = re.compile(r"\b(?:задач\w*|разов\w*)\b", re.IGNORECASE)
EXPLICIT_ROUTINE_RE = re.compile(
    r"\b(?:кажд\w+\s+день|ежедневн\w*|по\s+будням|регулярн\w*|напоминай)\b",
    re.IGNORECASE,
)
TIME_OR_DURATION_RE = re.compile(
    r"\b(?:сегодня|завтра|утром|дн[её]м|вечером|\d{1,2}:\d{2}|\d+\s*(?:мин|час))\b",
    re.IGNORECASE,
)
CANCEL_RE = re.compile(r"^\s*(?:отмена|отмени|не надо|ничего)\s*[.!]?\s*$", re.IGNORECASE)
KNOWN_ACRONYMS = {"api", "okr", "kpi", "бжу", "кбжу", "имт", "ндс"}


@dataclass(frozen=True)
class TrackingAmbiguity:
    subject: str
    one_time_title: str
    routine_title: str


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \n\t.,;:—-")


def _looks_like_acronym(token: str) -> bool:
    letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", token)
    return letters.lower() in KNOWN_ACRONYMS or (
        2 <= len(letters) <= 6
        and not re.search(r"[аеёиоуыэюяaeiouy]", letters, re.IGNORECASE)
    )


def _display_subject(value: str) -> str:
    words = []

    for word in _normalize_spaces(value).split():
        words.append(word.upper() if _looks_like_acronym(word) else word.lower())

    return " ".join(words)


def normalize_task_title(value: str) -> str:
    title = _normalize_spaces(value)
    title = COMMAND_PREFIX_RE.sub("", title)
    title = REPLAN_SUFFIX_RE.sub("", title)
    title = _normalize_spaces(title)

    if not title:
        return ""

    return title[0].upper() + title[1:]


def normalize_routine_title(value: str) -> str:
    title = _normalize_spaces(value)
    title = re.sub(
        r"^(?:кажд\w+\s+день|ежедневн\w*|по\s+будням|регулярн\w*|"
        r"по\s+(?:понедельникам|вторникам|средам|четвергам|пятницам|субботам|воскресеньям))\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"^(?:напоминай|напомни|нужно|хочу)\s+(?:мне\s+)?",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return normalize_task_title(title)


def normalize_parsed_tasks(parsed_message: ParsedUserMessage, source_text: str) -> None:
    for task in parsed_message.tasks:
        task.title = normalize_task_title(task.title)

        if task.referenced_task_title:
            task.referenced_task_title = normalize_task_title(task.referenced_task_title)

        if task.operation == "create" and not task.title:
            task.needs_clarification = True
            task.clarification_reason = "Не получилось определить название задачи. Что именно добавить?"

    parsed_message.raw_text = source_text


def is_cancel_message(text: str) -> bool:
    return bool(CANCEL_RE.fullmatch(text))


def is_explicit_routine_request(text: str) -> bool:
    return bool(EXPLICIT_ROUTINE_RE.search(text))


def is_capability_request(text: str) -> bool:
    lowered = text.lower().replace("ё", "е")
    asks_to_build = bool(re.search(r"\b(?:сделай|создай|добавь|хочу|нужен|нужна)\b", lowered))
    return asks_to_build and bool(CAPABILITY_RE.search(lowered)) and not EXPLICIT_TASK_RE.search(lowered)


def detect_tracking_ambiguity(
    text: str,
    parsed_message: ParsedUserMessage,
) -> TrackingAmbiguity | None:
    if parsed_message.intent != "add_tasks" or not parsed_message.tasks:
        return None

    if is_capability_request(text) or EXPLICIT_TASK_RE.search(text) or EXPLICIT_ROUTINE_RE.search(text):
        return None

    if TIME_OR_DURATION_RE.search(text) or not TRACKING_RE.search(text):
        return None

    if not re.search(r"\b(?:добавь|добавить|сделай|создай|хочу)\b", text, re.IGNORECASE):
        return None

    subject = COMMAND_PREFIX_RE.sub("", text)
    subject = re.split(
        r"\b(?:чтобы|для\s+того\s+чтобы|котор\w*|считать|считал\w*|отслеживать|уч[её]т|"
        r"записывать|фиксировать)\b",
        subject,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    subject = _display_subject(subject)

    if not subject:
        return None

    return TrackingAmbiguity(
        subject=subject,
        one_time_title=f"Записать {subject}",
        routine_title=f"Записывать {subject}",
    )


def is_low_energy_replan_request(text: str, parsed_message: ParsedUserMessage) -> bool:
    if parsed_message.energy_level != "low":
        return False

    normalized = text.lower().replace("ё", "е")
    return any(
        phrase in normalized
        for phrase in [
            "оставь только главное",
            "оставить только главное",
            "оставь только важное",
            "оставить только важное",
            "убери лишнее",
        ]
    )


def interaction_option(options: list[dict], option_id: str | None, text: str) -> str | None:
    normalized = _normalize_spaces(text).lower().replace("ё", "е")

    for option in options:
        option_label = _normalize_spaces(str(option.get("label", ""))).lower().replace("ё", "е")
        option_value = _normalize_spaces(str(option.get("value", ""))).lower().replace("ё", "е")

        if option_id == option.get("id") or normalized in {option_label, option_value}:
            return str(option.get("id"))

    return option_id


def task_for_one_time_tracking(title: str, target_date: str = "today") -> ParsedTask:
    return ParsedTask(
        title=title,
        operation="create",
        scheduling_type="unscheduled",
        target_date=target_date,
        estimated_minutes=None,
    )
