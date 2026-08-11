from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import event, func, select

from app.models.evidence import Evidence, GoalProgressSnapshot
from app.models.goal import Goal
from app.models.program import GoalMilestone, Program, ProgramPhase, WeeklyCommitment
from app.models.user import User
from app.services import path_service
from tests.test_api_v2_auth import api, bearer, begin_apple_sign_in


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def stable_path_clock(monkeypatch) -> None:
    monkeypatch.setattr(path_service, "get_user_now", lambda _user: NOW)


def seed_path(factory, *, owner_public_id: str, other_public_id: str | None = None):
    with factory() as db:
        owner = db.scalar(
            select(User).where(User.public_id == UUID(owner_public_id))
        )
        assert owner is not None
        high = Goal(
            user_id=owner.id,
            title="Выйти на измеримый результат",
            life_area="career",
            priority="high",
            status="active",
            outcome_type="metric",
            baseline_value=Decimal("10"),
            current_value=Decimal("15"),
            target_value=Decimal("20"),
            metric_unit="units",
        )
        medium = Goal(
            user_id=owner.id,
            title="Завершить важные этапы",
            life_area="mind",
            priority="medium",
            status="active",
            outcome_type="milestone",
        )
        low = Goal(
            user_id=owner.id,
            title="Соблюдать ритм",
            life_area="body",
            priority="low",
            status="active",
            outcome_type="consistency",
        )
        overflow = Goal(
            user_id=owner.id,
            title="Не должна попасть в первые три",
            life_area="personal",
            priority="low",
            status="active",
            outcome_type="consistency",
        )
        db.add_all([high, medium, low, overflow])
        db.flush()
        db.add_all(
            [
                GoalMilestone(
                    user_id=owner.id,
                    goal_id=high.id,
                    title="Второй этап",
                    position=2,
                    criteria={"kind": "manual_confirmation"},
                    status="pending",
                ),
                GoalMilestone(
                    user_id=owner.id,
                    goal_id=high.id,
                    title="Первый этап",
                    position=1,
                    criteria={"kind": "manual_confirmation"},
                    status="completed",
                    completed_at=NOW - timedelta(days=2),
                ),
            ]
        )
        archived = Program(
            user_id=owner.id,
            goal_id=high.id,
            name="Старая программа",
            status="archived",
            minimum_minutes_week=30,
            comfortable_minutes_week=60,
            maximum_minutes_week=90,
            adaptation_rules={},
        )
        program = Program(
            user_id=owner.id,
            goal_id=high.id,
            name="Текущая программа",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={},
        )
        db.add_all([archived, program])
        db.flush()
        phase = ProgramPhase(
            user_id=owner.id,
            program_id=program.id,
            title="Текущая фаза",
            position=1,
            status="active",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 9, 1),
            configuration={},
        )
        future_phase = ProgramPhase(
            user_id=owner.id,
            program_id=program.id,
            title="Следующая фаза",
            position=2,
            status="planned",
            start_date=date(2026, 9, 2),
            end_date=date(2026, 10, 1),
            configuration={},
        )
        db.add_all([phase, future_phase])
        db.flush()
        commitment = WeeklyCommitment(
            user_id=owner.id,
            goal_id=high.id,
            program_id=program.id,
            phase_id=phase.id,
            title="Сделать следующий измеримый шаг",
            target_minutes_week=120,
            target_sessions_week=3,
            minimum_block_minutes=30,
            allowed_weekdays=[1, 3, 5],
            preferred_window="evening",
            active=True,
        )
        db.add(commitment)
        db.add_all(
            [
                GoalProgressSnapshot(
                    user_id=owner.id,
                    goal_id=high.id,
                    as_of=NOW - timedelta(days=2),
                    strategy="metric",
                    percentage=Decimal("40"),
                    components={"baseline": "10", "current": "14", "target": "20"},
                    formula_version="progress-v1",
                    confidence="medium",
                ),
                GoalProgressSnapshot(
                    user_id=owner.id,
                    goal_id=high.id,
                    as_of=NOW,
                    strategy="metric",
                    percentage=Decimal("50"),
                    components={"baseline": "10", "current": "15", "target": "20"},
                    formula_version="progress-v1",
                    forecast_date=date(2026, 9, 10),
                    confidence="high",
                ),
                GoalProgressSnapshot(
                    user_id=owner.id,
                    goal_id=low.id,
                    as_of=NOW,
                    strategy="consistency",
                    percentage=None,
                    components={"planned_sessions": 12, "completed_sessions": 0},
                    reason="insufficient_data",
                    formula_version="progress-v1",
                    confidence="low",
                ),
            ]
        )
        for index in range(5):
            db.add(
                Evidence(
                    user_id=owner.id,
                    goal_id=high.id,
                    program_id=program.id,
                    commitment_id=commitment.id,
                    request_id=f"path-evidence-{index}",
                    evidence_type="partial" if index == 0 else "session",
                    quantity=Decimal(str(10 + index)),
                    unit="units",
                    occurred_at=NOW - timedelta(hours=index),
                    note=f"СЕКРЕТНАЯ ЗАМЕТКА {index}",
                    attributes={"private_health_like_value": index},
                )
            )
        if other_public_id is not None:
            other = db.scalar(
                select(User).where(User.public_id == UUID(other_public_id))
            )
            assert other is not None
            private_goal = Goal(
                user_id=other.id,
                title="Чужая приватная цель",
                priority="high",
                status="active",
                outcome_type="consistency",
            )
            db.add(private_goal)
        db.commit()
        return {
            "high": str(high.public_id),
            "medium": str(medium.public_id),
            "low": str(low.public_id),
            "overflow": str(overflow.public_id),
            "program": str(program.id),
            "phase": str(phase.id),
            "commitment": str(commitment.id),
        }


def test_path_is_authoritative_bounded_and_omits_sensitive_evidence(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-path-owner"
    )
    other = begin_apple_sign_in(
        client, identity_token="valid-identity-token-path-other"
    )
    ids = seed_path(
        factory,
        owner_public_id=owner["user"]["public_id"],
        other_public_id=other["user"]["public_id"],
    )
    engine = factory.kw["bind"]
    statements: list[str] = []

    def count_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        response = client.get(
            "/api/v2/path", headers=bearer(owner["access_token"])
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["goal"]["public_id"] for item in payload["goals"]] == [
        ids["high"],
        ids["medium"],
        ids["low"],
    ]
    assert ids["overflow"] not in response.text
    assert "Чужая приватная цель" not in response.text
    assert len(statements) <= 12
    evidence_queries = [
        statement.lower()
        for statement in statements
        if " evidence" in statement.lower()
    ]
    assert evidence_queries
    assert all("evidence.note" not in statement for statement in evidence_queries)
    assert all("evidence.attributes" not in statement for statement in evidence_queries)
    bounded_history_queries = [
        statement.lower()
        for statement in statements
        if "evidence" in statement.lower()
        or "goal_progress_snapshots" in statement.lower()
    ]
    assert all("row_number()" not in statement for statement in bounded_history_queries)

    first = payload["goals"][0]
    assert first["progress"]["percentage"] == "50.0000"
    assert first["progress"]["forecast_date"] == "2026-09-10"
    assert first["progress"]["confidence"] == "high"
    assert first["formula"]["strategy"] == "metric"
    assert first["formula"]["label"]
    assert first["formula"]["explanation"]
    assert first["current_program"]["id"] == ids["program"]
    assert first["current_phase"]["id"] == ids["phase"]
    assert first["next_step"]["commitment_id"] == ids["commitment"]
    assert [item["position"] for item in first["milestones"]] == [1, 2]
    assert len(first["recent_evidence"]) == 3
    assert "note" not in first["recent_evidence"][0]
    assert "attributes" not in first["recent_evidence"][0]
    assert "СЕКРЕТНАЯ ЗАМЕТКА" not in response.text
    assert "private_health_like_value" not in response.text

    second = payload["goals"][1]
    assert second["progress"]["percentage"] is None
    assert second["progress"]["reason"] == "not_calculated"
    assert second["formula"]["label"] == "Недостаточно данных"
    assert "Процент" in second["formula"]["explanation"]
    third = payload["goals"][2]
    assert third["progress"]["reason"] == "insufficient_data"
    assert third["formula"]["label"] == "Недостаточно данных"


def test_goal_detail_is_read_only_and_cross_user_is_opaque(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-detail-owner"
    )
    other = begin_apple_sign_in(
        client, identity_token="valid-identity-token-detail-other"
    )
    ids = seed_path(
        factory,
        owner_public_id=owner["user"]["public_id"],
        other_public_id=other["user"]["public_id"],
    )
    with factory() as db:
        before = db.scalar(select(func.count(GoalProgressSnapshot.id)))

    detail = client.get(
        f"/api/v2/goals/{ids['high']}",
        headers=bearer(owner["access_token"]),
    )
    hidden = client.get(
        f"/api/v2/goals/{ids['high']}",
        headers=bearer(other["access_token"]),
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["goal"]["public_id"] == ids["high"]
    assert detail.json()["current_program"]["name"] == "Текущая программа"
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Goal not found"
    with factory() as db:
        after = db.scalar(select(func.count(GoalProgressSnapshot.id)))
    assert after == before


@pytest.mark.parametrize(
    ("phase_start", "phase_end"),
    [
        (NOW.date() - timedelta(days=60), NOW.date() - timedelta(days=30)),
        (NOW.date() + timedelta(days=30), NOW.date() + timedelta(days=60)),
    ],
)
def test_goal_detail_does_not_call_stale_or_future_phase_current(
    api,
    phase_start: date,
    phase_end: date,
) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token=f"valid-identity-token-phase-{phase_start}"
    )
    ids = seed_path(factory, owner_public_id=owner["user"]["public_id"])
    with factory() as db:
        phase = db.get(ProgramPhase, UUID(ids["phase"]))
        assert phase is not None
        phase.start_date = phase_start
        phase.end_date = phase_end
        phase.status = "active"
        db.commit()

    response = client.get(
        f"/api/v2/goals/{ids['high']}",
        headers=bearer(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["current_phase"] is None
    assert response.json()["next_step"] is None


def test_evidence_uses_stable_cursor_pagination_without_notes(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-evidence-page-owner"
    )
    other = begin_apple_sign_in(
        client, identity_token="valid-identity-token-evidence-page-other"
    )
    ids = seed_path(
        factory,
        owner_public_id=owner["user"]["public_id"],
        other_public_id=other["user"]["public_id"],
    )
    with factory() as db:
        goal = db.scalar(
            select(Goal).where(Goal.public_id == UUID(ids["high"]))
        )
        assert goal is not None
        evidence = list(
            db.scalars(
                select(Evidence)
                .where(Evidence.goal_id == goal.id)
                .order_by(Evidence.occurred_at.desc())
            ).all()
        )
        for item in evidence[:3]:
            item.occurred_at = NOW
        tied_ids = sorted((item.id for item in evidence[:3]), reverse=True)
        db.commit()
    headers = bearer(owner["access_token"])

    first = client.get(
        f"/api/v2/goals/{ids['high']}/evidence?limit=2", headers=headers
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert len(first_payload["items"]) == 2
    assert first_payload["next_cursor"]
    assert all("note" not in item and "attributes" not in item for item in first_payload["items"])

    second = client.get(
        f"/api/v2/goals/{ids['high']}/evidence",
        params={"limit": 2, "cursor": first_payload["next_cursor"]},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    third = client.get(
        f"/api/v2/goals/{ids['high']}/evidence",
        params={"limit": 2, "cursor": second_payload["next_cursor"]},
        headers=headers,
    )
    assert third.status_code == 200, third.text
    third_payload = third.json()

    all_ids = [
        item["id"]
        for page in (first_payload, second_payload, third_payload)
        for item in page["items"]
    ]
    assert len(all_ids) == 5
    assert len(set(all_ids)) == 5
    assert [UUID(item) for item in all_ids[:3]] == tied_ids
    assert third_payload["next_cursor"] is None
    assert "СЕКРЕТНАЯ ЗАМЕТКА" not in first.text + second.text + third.text

    invalid = client.get(
        f"/api/v2/goals/{ids['high']}/evidence",
        params={"cursor": "not-a-valid-cursor"},
        headers=headers,
    )
    hidden = client.get(
        f"/api/v2/goals/{ids['high']}/evidence",
        headers=bearer(other["access_token"]),
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "invalid_cursor"
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Goal not found"


@pytest.mark.parametrize(
    ("goal_key", "strategy", "reason", "expected_label", "expected_copy"),
    [
        (
            "high",
            "metric",
            "invalid_target",
            "Нужно уточнить цель",
            "исходного и целевого значений",
        ),
        (
            "medium",
            "milestone",
            "invalid_milestone_weights",
            "Нужно исправить веса этапов",
            "веса всех этапов",
        ),
    ],
)
def test_formula_explains_configuration_errors_instead_of_requesting_more_data(
    api,
    goal_key: str,
    strategy: str,
    reason: str,
    expected_label: str,
    expected_copy: str,
) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token=f"valid-identity-token-formula-{reason}"
    )
    ids = seed_path(factory, owner_public_id=owner["user"]["public_id"])
    with factory() as db:
        goal = db.scalar(
            select(Goal).where(Goal.public_id == UUID(ids[goal_key]))
        )
        assert goal is not None
        db.add(
            GoalProgressSnapshot(
                user_id=goal.user_id,
                goal_id=goal.id,
                as_of=NOW + timedelta(minutes=1),
                strategy=strategy,
                percentage=None,
                components={},
                reason=reason,
                formula_version="progress-v1",
                confidence="low",
            )
        )
        db.commit()

    response = client.get(
        f"/api/v2/goals/{ids[goal_key]}",
        headers=bearer(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    formula = response.json()["formula"]
    assert formula["label"] == expected_label
    assert expected_copy in formula["explanation"]


def test_path_requires_auth_and_empty_state_is_typed(api) -> None:
    client, _factory = api
    unauthorized = client.get("/api/v2/path")
    signed_in = begin_apple_sign_in(
        client, identity_token="valid-identity-token-empty-path"
    )
    empty = client.get(
        "/api/v2/path", headers=bearer(signed_in["access_token"])
    )

    assert unauthorized.status_code == 401
    assert empty.status_code == 200
    assert empty.json() == {"goals": []}


def test_path_history_indexes_match_top_n_access_patterns() -> None:
    evidence_indexes = {
        tuple(column.name for column in index.columns)
        for index in Evidence.__table__.indexes
    }
    progress_indexes = {
        tuple(column.name for column in index.columns)
        for index in GoalProgressSnapshot.__table__.indexes
    }

    assert ("user_id", "goal_id", "occurred_at", "id") in evidence_indexes
    assert (
        "user_id",
        "goal_id",
        "as_of",
        "created_at",
        "id",
    ) in progress_indexes
