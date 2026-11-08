import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from lease.domain import EventType, Fact, apply_fact, freshness_outcome


class Conflict(Exception):
    pass


def make_pool():
    return ConnectionPool(
        os.environ["DATABASE_URL"],
        min_size=0,
        max_size=int(os.getenv("DB_POOL_SIZE", "5")),
        timeout=0.5,
        kwargs={"row_factory": dict_row, "connect_timeout": 2,
                "options": "-c statement_timeout=1500 -c lock_timeout=1000"},
        open=True,
    )


def ingest(db, fact: Fact, request_id: str):
    with db.connection() as conn:
        # Serialize retries of an event ID before allocating a lease version.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                     (str(fact.event_id),))
        existing = conn.execute(
            "SELECT driver_id, event_type, version FROM facts WHERE event_id = %s",
            (fact.event_id,),
        ).fetchone()
        if existing:
            if (existing["driver_id"], existing["event_type"]) != (
                fact.driver_id, fact.event_type
            ):
                raise Conflict
            return existing["version"]
        version = conn.execute(
            """INSERT INTO lease_sequence VALUES (%s, 1)
               ON CONFLICT (driver_id) DO UPDATE SET version = lease_sequence.version + 1
               RETURNING version""", (fact.driver_id,),
        ).fetchone()["version"]
        conn.execute(
            """INSERT INTO facts(event_id, driver_id, event_type, version, request_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (fact.event_id, fact.driver_id, fact.event_type, version, request_id),
        )
        return version


def get_lease(db, driver_id):
    with db.connection() as conn:
        return conn.execute("SELECT * FROM lease_view WHERE driver_id = %s",
                            (driver_id,)).fetchone()


def project(db, event_id):
    with db.connection() as conn:
        fact = conn.execute("SELECT * FROM facts WHERE event_id = %s FOR UPDATE",
                            (event_id,)).fetchone()
        if fact is None:
            raise ValueError("Unknown fact")
        if fact["projected_at"] is not None:
            return fact, "duplicate"
        driver = fact["driver_id"]
        conn.execute("SELECT 1 FROM lease_sequence WHERE driver_id = %s FOR UPDATE", (driver,))
        state = conn.execute("SELECT * FROM lease_view WHERE driver_id = %s",
                             (driver,)).fetchone()
        version = fact["version"]
        if version != (state["version"] if state else 0) + 1:
            raise ValueError("Lease version gap")
        status, cycle = apply_fact(state["payment_cycle"] if state else 0,
                                   EventType(fact["event_type"]))
        conn.execute(
            """INSERT INTO lease_view VALUES (%s, %s, %s, %s)
               ON CONFLICT (driver_id) DO UPDATE SET status = excluded.status,
               payment_cycle = excluded.payment_cycle, version = excluded.version""",
            (driver, status, cycle, version),
        )
        conn.execute("UPDATE facts SET projected_at = clock_timestamp() WHERE event_id = %s",
                     (event_id,))
        return fact, "applied"


def score(db):
    with db.connection() as conn:
        rows = conn.execute(
            """SELECT event_id, projected_at, accepted_at + interval '30 seconds' AS deadline
               FROM facts WHERE NOT scored AND event_type = 'payment_made'
               AND accepted_at <= now() - interval '30 seconds'
               ORDER BY accepted_at LIMIT 500 FOR UPDATE SKIP LOCKED"""
        ).fetchall()
        totals = {"good": 0, "bad": 0}
        for row in rows:
            totals[freshness_outcome(row["projected_at"], row["deadline"])] += 1
        if rows:
            conn.execute("UPDATE facts SET scored = true WHERE event_id = ANY(%s)",
                         ([row["event_id"] for row in rows],))
            for outcome, total in totals.items():
                conn.execute("UPDATE freshness_totals SET total = total + %s WHERE outcome = %s",
                             (total, outcome))
