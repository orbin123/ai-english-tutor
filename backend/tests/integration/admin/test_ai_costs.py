"""Phase 5 (5.3) — admin AI-cost report.

Verifies ``AdminService.ai_costs`` aggregates ai_request_logs into per-model /
per-capability / daily spend, deriving cost from the LLM pricing table
(gpt-4o-mini = $0.15/$0.60 per 1M in/out; gpt-4o = $2.50/$10.00). Models not in
the table are counted as ``unpriced_requests`` with no cost.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (populate the mapper registry)
from app.core.database import Base
from app.modules.admin.models import AIRequestLog
from app.modules.admin.service import AdminService
from app.modules.auth.models import User

# Anchor generated rows at noon yesterday so the 1-hour and 2-hour samples
# always share a UTC date, including when the suite runs around midnight.
NOW = datetime.now(timezone.utc).replace(
    hour=12, minute=0, second=0, microsecond=0
) - timedelta(days=1)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, AIRequestLog.__table__])
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


def _log(db, *, agent, model, in_tok, out_tok, status="success", hours_ago=1):
    db.add(
        AIRequestLog(
            user_id=None,
            agent_name=agent,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            status=status,
            latency_ms=100,
            created_at=NOW - timedelta(hours=hours_ago),
        )
    )
    db.flush()


def test_ai_costs_aggregates_cost_per_model_and_capability(db):
    _log(db, agent="teacher", model="gpt-4o-mini", in_tok=1_000_000, out_tok=1_000_000)
    _log(db, agent="teacher", model="gpt-4o-mini", in_tok=0, out_tok=0, status="error")
    _log(db, agent="evaluator", model="gpt-4o", in_tok=1_000_000, out_tok=0)
    _log(db, agent="evaluator", model="unknown-model", in_tok=500, out_tok=500)

    report = AdminService(db).ai_costs(days=30)

    # Totals: 0.75 (mini) + 2.50 (4o) + 0 (error) + 0 (unpriced) = 3.25.
    assert report.total_requests == 4
    assert report.total_cost_usd == pytest.approx(3.25)
    assert report.total_input_tokens == 2_000_500
    assert report.total_output_tokens == 1_000_500
    assert report.unpriced_requests == 1

    by_model = {m.model: m for m in report.by_model}
    assert by_model["gpt-4o-mini"].cost_usd == pytest.approx(0.75)
    assert by_model["gpt-4o-mini"].requests == 2
    assert by_model["gpt-4o"].cost_usd == pytest.approx(2.50)
    assert by_model["unknown-model"].cost_usd is None  # not in pricing table
    # Sorted by cost desc: gpt-4o first.
    assert report.by_model[0].model == "gpt-4o"

    by_cap = {c.agent_name: c for c in report.by_capability}
    assert by_cap["teacher"].cost_usd == pytest.approx(0.75)
    assert by_cap["teacher"].errors == 1
    assert by_cap["teacher"].requests == 2
    assert by_cap["evaluator"].cost_usd == pytest.approx(2.50)
    assert by_cap["evaluator"].errors == 0
    # Sorted by cost desc: evaluator first.
    assert report.by_capability[0].agent_name == "evaluator"


def test_ai_costs_daily_rolls_up_per_day(db):
    _log(
        db,
        agent="teacher",
        model="gpt-4o-mini",
        in_tok=1_000_000,
        out_tok=0,
        hours_ago=1,
    )
    _log(db, agent="teacher", model="gpt-4o", in_tok=1_000_000, out_tok=0, hours_ago=2)
    # Two days back — its own bucket.
    _log(
        db,
        agent="teacher",
        model="gpt-4o-mini",
        in_tok=1_000_000,
        out_tok=0,
        hours_ago=49,
    )

    report = AdminService(db).ai_costs(days=30)

    assert len(report.daily) == 2
    # Oldest first.
    assert report.daily[0].date < report.daily[1].date
    # Latest bucket: 0.15 (mini in) + 2.50 (4o in) = 2.65, 2 requests.
    latest = report.daily[-1]
    assert latest.requests == 2
    assert latest.cost_usd == pytest.approx(2.65)


def test_ai_costs_window_excludes_old_rows(db):
    _log(
        db,
        agent="teacher",
        model="gpt-4o-mini",
        in_tok=1_000_000,
        out_tok=0,
        hours_ago=1,
    )
    _log(
        db,
        agent="teacher",
        model="gpt-4o-mini",
        in_tok=1_000_000,
        out_tok=0,
        hours_ago=24 * 40,
    )

    report = AdminService(db).ai_costs(days=30)

    assert report.total_requests == 1  # the 40-day-old row is outside the window
