import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.bot.main as bot_main
import app.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.models.task import Task
from app.models.user import User
from app.services.user_service import get_or_create_user


class FakeTelegramUser:
    id = 12345
    full_name = "Telegram User"


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.from_user = FakeTelegramUser()
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


@pytest.fixture()
def db_session_factory(tmp_path: Path, monkeypatch) -> Generator[sessionmaker[Session], None, None]:
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    database_path = tmp_path / "telegram-handler-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(bot_main, "SessionLocal", TestingSessionLocal)

    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)


def test_text_handler_uses_shared_pipeline_without_duplicating_telegram_user(
    db_session_factory: sessionmaker[Session],
):
    with db_session_factory() as db:
        get_or_create_user(
            db=db,
            telegram_id=FakeTelegramUser.id,
            name=FakeTelegramUser.full_name,
        )

    message = FakeMessage("Сегодня хочу разобрать документы")

    asyncio.run(bot_main.handle_text_message(message))

    assert len(message.answers) == 1
    assert "Принял" in message.answers[0]

    with db_session_factory() as db:
        users = db.query(User).all()
        tasks = db.query(Task).all()

    assert len(users) == 1
    assert users[0].telegram_id == FakeTelegramUser.id
    assert users[0].external_id == f"telegram:{FakeTelegramUser.id}"
    assert [task.title for task in tasks] == ["разобрать документы"]
    assert tasks[0].user_id == users[0].id
