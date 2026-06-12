from sqlalchemy.orm import Session

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
        lines.append(f"{goal.id}. {goal.title} — {goal.priority}")

    return "\n".join(lines)
