from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so Alembic can detect them through Base.metadata.
from app.models.user import User  # noqa: E402,F401
from app.models.goal import Goal  # noqa: E402,F401
from app.models.task import Task  # noqa: E402,F401
from app.models.day_plan import DayPlan  # noqa: E402,F401
from app.models.plan_item import PlanItem  # noqa: E402,F401
