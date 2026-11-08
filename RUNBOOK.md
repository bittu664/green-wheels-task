# Fleet Lease Incident Runbook

For every incident, record the UTC start time, deploy revision, affected endpoints,
and the oldest affected payment. The primary owns mitigation and the secondary
handles communication. Confirm accepted payment facts and final lease state before closure.

## Lease event processing backlog

**Detection.** Freshness fast burn or old pending payments. Rising Kafka group lag
points to the projector. Old unpublished facts with stable Kafka lag point to the
publisher or broker path.

**Immediate triage.** Check the Grafana backlog, outbox, and per-partition lag panels.
Compare with the last ECS deployment. Confirm whether ingestion is still accepting
durable facts. Notify Fleet Ops if drivers see stale payment status.

**Diagnosis.** Use the approved broker authentication configuration on AWS.

```sh
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 --describe --group lease-projector
docker compose logs --since 15m publisher projector evaluator
docker compose exec db psql -U lease -d lease -c \
  "SELECT event_id, driver_id, version, accepted_at, published_at
   FROM facts WHERE projected_at IS NULL ORDER BY accepted_at LIMIT 20;"
aws ecs describe-services --cluster "$CLUSTER" --services "$PROJECTOR_SERVICE"
```

**Resolution.** Restore broker connectivity if the outbox is accumulating. Roll back
a regressed projector and verify the group stabilizes. Add consumers only if lag spans
multiple partitions and the database has capacity. If a malformed fact or version gap
blocks progress, preserve the event and offset, repair the cause with the service owner,
and resume from committed offsets. Audit accepted versus projected facts. Verify the
oldest pending age falls, the group catches up, and the affected driver's lease agrees
with the fact log.

**Escalation.** Bring in secondary after 10 minutes without containment, immediately
if payment integrity is uncertain, and involve the Kafka owner for broker or
partition failures. Fleet Ops owns driver-facing communications.

**Local drill.** Process one event first so the group has offsets. Stop the projector
with `docker compose stop projector`, submit several new payment facts, and observe
the lag and pending age. Leave it stopped for over five minutes to exercise the
backlog warning. Start it with `docker compose start projector` and verify each payment
applied exactly once. Late facts remain bad in the historical SLI.

## Database connection pool exhaustion

**Detection.** Pool timeout logs, elevated RDS connections, readiness failure, and
5xx responses from both lease endpoints. The demo maps recognized database failures
to 503 so callers can retry with the same event ID.

**Immediate triage.** Check if API tasks doubled during rollout. Compare connection
count to the RDS limit and inspect active queries, pool timeouts, and locks. Pause the
release if it coincides with the incident. Reduce avoidable background load while
keeping the fact log intact.

**Diagnosis.** Use a reserved operations connection and an approved read-only role.

```sql
SHOW max_connections;
SELECT application_name, state, count(*)
FROM pg_stat_activity GROUP BY 1, 2 ORDER BY 3 DESC;
SELECT pid, application_name, state, wait_event,
       now() - xact_start AS transaction_age, pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity WHERE datname = current_database()
ORDER BY xact_start NULLS LAST LIMIT 30;
```

```sh
docker compose logs --since 15m api | grep db_pool_timeout
aws ecs describe-services --cluster "$CLUSTER" --services "$API_SERVICE"
```

**Resolution.** Roll back the connection or query regression. Pause the confirmed
offending batch workload. Cancel a confirmed runaway query with `pg_cancel_backend`
after assessing its transaction and business impact. Reduce per-task pools or
deployment overlap if aggregate pool capacity exceeds available DB connections.
Confirm readiness, accept and verify a synthetic payment, and check RDS headroom
after the queue drains.

**Escalation.** Secondary joins at 10 minutes without containment. Escalate immediately
to the DB owner for failover, widespread blocked writes, or suspected corruption.
Notify Fleet Ops of any driver impact.

**Local drill.** For the demo database only, hold an exclusive lock on
`lease_sequence` with `BEGIN; LOCK TABLE lease_sequence IN ACCESS EXCLUSIVE MODE;
SELECT pg_sleep(20); ROLLBACK;` in one session. Drive concurrent GET /health
requests in another terminal. SQL lock timeouts and limited pool slots should
surface 503 responses and, at sufficient concurrency, pool timeout logs. Confirm
recovery after the lock releases.

## Ingestion errors

Check POST status classes and the recent release. Correlate request IDs with
`db_pool_timeout` and `db_unavailable`. If the database is saturated, follow
[pool exhaustion](#database-connection-pool-exhaustion). Verify recovery with an
idempotent POST and confirm its version projects.

## Lease read latency

Compare read p95 with 30-day budget and current server errors. Check PostgreSQL
locks, query latency, connection waits, and ECS CPU. Roll back a recent regression
or relieve the bottleneck. Validate with a real projection lookup.

## Service unavailable

Check whether /live responds while /health fails. Inspect ALB target reason codes,
ECS events, database connectivity, and the most recent task revision. Restore the
failing dependency or roll back a bad revision. Verify successful external probes.

## Monitoring missing

Check Prometheus Targets and exporter logs. Check service discovery and the network
path from Prometheus, then verify a fresh scrape. Confirm application health
separately while telemetry is degraded.
