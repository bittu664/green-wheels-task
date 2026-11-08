import json
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

REQUESTS = Counter("lease_http_requests", "Completed HTTP requests",
                   ["method", "route", "status_class", "outcome"])
DURATION = Histogram("lease_http_duration_seconds", "HTTP duration",
                     ["method", "route", "outcome"],
                     buckets=(.025, .05, .1, .2, .3, .5, 1, 2, 5))
PROJECTED = Counter("lease_projector_events", "Projector outcomes",
                    ["event_type", "outcome"])


def log(kind, **fields):
    print(json.dumps({"timestamp": datetime.now(UTC).isoformat(),
                      "kind": kind, **fields}, default=str), flush=True)


class DatabaseMetrics:
    def __init__(self, db):
        self.db = db

    def collect(self):
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM freshness_totals").fetchall()
            ages = conn.execute(
                """SELECT
                COALESCE(EXTRACT(EPOCH FROM now() - min(accepted_at)
                    FILTER (WHERE published_at IS NULL)), 0) AS outbox,
                COALESCE(EXTRACT(EPOCH FROM now() - min(accepted_at)
                    FILTER (WHERE projected_at IS NULL AND event_type = 'payment_made')), 0)
                    AS payment
                FROM facts WHERE projected_at IS NULL OR published_at IS NULL"""
            ).fetchone()
        metric = CounterMetricFamily("lease_payment_deadlines", "Scored payment facts",
                                     labels=["outcome"])
        for row in rows:
            metric.add_metric([row["outcome"]], row["total"])
        yield metric
        yield GaugeMetricFamily("lease_oldest_outbox_seconds", "Oldest unpublished fact",
                                value=float(ages["outbox"]))
        yield GaugeMetricFamily("lease_oldest_pending_payment_seconds",
                                "Oldest unapplied payment", value=float(ages["payment"]))

# Expose zero-valued series before the first request so rate/increase has a baseline.
for method, route, statuses in (
    ("POST", "/leases/events", (("2xx", "good"), ("5xx", "bad"), ("4xx", "bad"))),
    ("GET", "/leases/{driver_id}", (("2xx", "good"), ("4xx", "good"),
                                 ("5xx", "bad"), ("4xx", "bad"))),
):
    for status_class, outcome in statuses:
        REQUESTS.labels(method, route, status_class, outcome)
        DURATION.labels(method, route, outcome)
