import os
import signal
import sys
from threading import Event

from confluent_kafka import Consumer, Producer
from prometheus_client import CollectorRegistry, REGISTRY, start_http_server

from lease.store import make_pool, project, score
from lease.telemetry import DatabaseMetrics, log, PROJECTED

TOPIC = "lease-facts"
STOP = Event()


def publish(db, producer):
    with db.connection() as conn:
        # A transaction-scoped singleton lock keeps publish ordering during overlap.
        if not conn.execute("SELECT pg_try_advisory_xact_lock(20001) AS locked"
                            ).fetchone()["locked"]:
            return False
        row = conn.execute(
            """SELECT f.* FROM facts f WHERE f.published_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM facts p WHERE p.driver_id = f.driver_id
                   AND p.version = f.version - 1 AND p.published_at IS NULL)
               ORDER BY f.accepted_at LIMIT 1"""
        ).fetchone()
        if row is None:
            return False
        errors = []
        producer.produce(TOPIC, key=row["driver_id"], value=str(row["event_id"]),
                         on_delivery=lambda error, _: errors.append(error) if error else None)
        if producer.flush(6) or errors:
            raise RuntimeError("Kafka delivery failed")
        conn.execute("UPDATE facts SET published_at = clock_timestamp() WHERE event_id = %s",
                     (row["event_id"],))
        return True


def main(role):
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    db = make_pool()
    kafka = {"bootstrap.servers": os.getenv("KAFKA_BROKERS", "kafka:29092")}
    producer = consumer = None
    if role == "publisher":
        producer = Producer({**kafka, "enable.idempotence": True, "message.timeout.ms": 5000})
    elif role == "projector":
        consumer = Consumer({**kafka, "group.id": "lease-projector",
                             "enable.auto.commit": False, "auto.offset.reset": "earliest"})
        consumer.subscribe([TOPIC])
        start_http_server(9100, registry=REGISTRY)
    elif role == "evaluator":
        registry = CollectorRegistry()
        registry.register(DatabaseMetrics(db))
        start_http_server(9100, registry=registry)
    else:
        raise ValueError("Unknown worker role")
    pending = None
    try:
        while not STOP.is_set():
            try:
                if role == "publisher":
                    if not publish(db, producer):
                        STOP.wait(.25)
                elif role == "evaluator":
                    score(db)
                    STOP.wait(1)
                else:
                    pending = pending if pending is not None else consumer.poll(.5)
                    if pending is None:
                        continue
                    if pending.error():
                        error = str(pending.error())
                        pending = None
                        raise RuntimeError(error)
                    fact, outcome = project(db, pending.value().decode())
                    consumer.commit(message=pending, asynchronous=False)
                    pending = None
                    PROJECTED.labels(fact["event_type"], outcome).inc()
                    log("projection", outcome=outcome, request_id=fact["request_id"],
                        driver_id=fact["driver_id"], event_type=fact["event_type"],
                        event_id=fact["event_id"])
            except Exception as exc:
                log("worker_error", role=role, error=type(exc).__name__,
                    partition=pending.partition() if pending is not None else None,
                    offset=pending.offset() if pending is not None else None)
                if consumer is not None and pending is not None:
                    # Rejoin and resume at the committed offset after a failed write or commit.
                    consumer.close()
                    consumer = Consumer({**kafka, "group.id": "lease-projector",
                                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
                    consumer.subscribe([TOPIC])
                    pending = None
                STOP.wait(2)
    finally:
        if consumer is not None:
            consumer.close()
        db.close()


if __name__ == "__main__":
    main(sys.argv[1])
