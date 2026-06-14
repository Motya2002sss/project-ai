from sqlalchemy.orm import Session

from app.llm.schemas import ParsedTask
from app.models.goal import Goal
from app.models.user import User


def create_goals_from_titles(
    db: Session,
    user: User,
    titles: list[str],
) -> list[Goal]:
    goals: list[Goal] = []

    for title in titles:
        normalized_title = title.strip()

        if not normalized_title:
            continue

        exists = (
            db.query(Goal)
            .filter(
                Goal.user_id == user.id,
                Goal.title.ilike(normalized_title),
                Goal.status == "active",
            )
            .one_or_none()
        )

        if exists:
            continue

        goal = Goal(
            user_id=user.id,
            title=normalized_title[:255],
            category="personal",
            priority="medium",
            status="active",
        )

        db.add(goal)
        goals.append(goal)

    db.commit()

    for goal in goals:
        db.refresh(goal)

    return goals


def list_active_goals(db: Session, user: User) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(
            Goal.user_id == user.id,
            Goal.status == "active",
        )
        .order_by(Goal.id.asc())
        .all()
    )


def format_goals(goals: list[Goal]) -> str:
    if not goals:
        return "Активных целей пока нет."

    lines = []

    for goal in goals:
        lines.append(f"{goal.id}. {goal.title}")

    return "\n".join(lines)


def suggest_tasks_from_goals(goals: list[Goal]) -> list[ParsedTask]:
    suggestions: list[ParsedTask] = []

    for goal in goals:
        title = goal.title.lower()

        if any(word in title for word in ["деньги", "финанс", "накоп", "сбереж", "долг", "бюджет"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один финансовый шаг по цели: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["уч", "язык", "курс", "экзам", "книг", "математ", "англий"]):
            suggestions.append(
                ParsedTask(
                    title=f"Позаниматься 30-45 минут по цели: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["здоров", "спорт", "трен", "зал", "жим", "бег", "сон"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать короткий шаг для здоровья/спорта: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["сем", "родител", "дет", "отношен", "друз"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один шаг для отношений: {goal.title}",
                    priority="medium",
                    estimated_minutes=30,
                )
            )
            continue

        if any(word in title for word in ["рис", "музык", "твор", "пис", "фото", "дизайн"]):
            suggestions.append(
                ParsedTask(
                    title=f"Выделить время на творческий шаг: {goal.title}",
                    priority="medium",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["проект", "прилож", "продукт", "стартап", "карьер", "работ"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один конкретный шаг по проекту/карьере: {goal.title}",
                    priority="high",
                    estimated_minutes=60,
                )
            )
            continue

        suggestions.append(
            ParsedTask(
                title=f"Сделать следующий маленький шаг по цели: {goal.title}",
                priority="medium",
                estimated_minutes=45,
            )
        )

    unique: list[ParsedTask] = []
    seen: set[str] = set()

    for task in suggestions:
        key = task.title.lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(task)

    return unique
