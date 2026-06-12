from sqlalchemy.orm import Session

from app.models.user import User


def get_or_create_user(
    db: Session,
    telegram_id: int,
    name: str | None = None,
) -> User:
    user = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()

    if user:
        if name and user.name != name:
            user.name = name
            db.commit()
            db.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        name=name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
