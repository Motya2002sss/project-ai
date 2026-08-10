from unittest.mock import MagicMock

from app.models.user import User
from app.services.interaction_service import get_pending_interaction


def test_pending_interaction_lookup_locks_selected_row(monkeypatch):
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.order_by.return_value = query
    query.first.return_value = None
    user = User(id=1, external_id="interaction-lock-user")
    monkeypatch.setattr(
        "app.services.interaction_service.expire_pending_interactions",
        lambda db, user: None,
    )

    get_pending_interaction(db, user, interaction_id="interaction-id")

    query.with_for_update.assert_called_once_with()
