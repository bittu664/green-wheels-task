from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from lease.domain import EventType, Fact, apply_fact, freshness_outcome
from lease.store import Conflict, ingest


def test_ingest_allocates_and_persists_version():
    pool = MagicMock()
    conn = pool.connection.return_value.__enter__.return_value
    conn.execute.return_value.fetchone.side_effect = [None, {"version": 7}]
    fact = Fact(event_id=uuid4(), driver_id="driver-1", event_type="payment_made")
    assert ingest(pool, fact, "req-1") == 7
    sql, params = conn.execute.call_args.args
    assert "INSERT INTO facts" in sql
    assert params == (fact.event_id, "driver-1", EventType.PAID, 7, "req-1")


def test_ingestion_retry_and_conflict():
    pool = MagicMock()
    conn = pool.connection.return_value.__enter__.return_value
    conn.execute.return_value.fetchone.return_value = {
        "driver_id": "driver-1", "event_type": "payment_made", "version": 4,
    }
    fact = Fact(event_id=uuid4(), driver_id="driver-1", event_type="payment_made")
    assert ingest(pool, fact, "req-2") == 4
    assert conn.execute.call_count == 2
    changed = fact.model_copy(update={"event_type": EventType.MISSED})
    with pytest.raises(Conflict):
        ingest(pool, changed, "req-3")
    assert conn.execute.call_count == 4


def test_payment_transition():
    assert apply_fact(3, EventType.PAID) == ("active", 4)
    assert apply_fact(4, EventType.MISSED) == ("overdue", 4)
    assert apply_fact(4, EventType.PAUSED) == ("paused", 4)


def test_payment_deadline_boundary_and_pending():
    deadline = datetime.now(UTC)
    assert freshness_outcome(deadline, deadline) == "good"
    assert freshness_outcome(deadline + timedelta(microseconds=1), deadline) == "bad"
    assert freshness_outcome(None, deadline) == "bad"
