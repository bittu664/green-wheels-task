# Fleet Lease at scale

Assumptions are 500,000 registered drivers, 50,000 active leases, and a 500 events/s
payment peak across eight countries. These are design inputs. The Compose stack
uses a singleton publisher and is not a capacity benchmark.

## Kafka ordering and consumer capacity

Partition by immutable lease ID, with one consumer group per projection. Choose
partition count from measured throughput per partition and leave spare capacity.
Scale tasks on oldest event age and lag growth, capped by partitions and database
headroom. Hot leases require reducing per-event work or revisiting the domain
ordering constraint. Avoid expanding partitions in place without a routing migration
plan because a lease key may move. At this scale, shard outbox publishers by lease
or use ordered CDC. Benchmark batching, retry behavior, and database lock waits.

## Read/write split

Index and profile the projection lookup first. Introduce a read replica when
reads measurably compete with write capacity. Route reporting and other
stale-tolerant reads to the replica. Send freshness-sensitive reads to the writer
or require a minimum projection version, subject to a bounded fallback budget.
Alert on replication delay and preserve writer headroom when a replica degrades.

## Cache

Cache only read projections, keyed by tenant and lease, with a short TTL and
version-aware writes or invalidations after projection commit. Use request
coalescing for hot misses. Prevent stale reads from repopulating the cache with
an older version. Read from a suitably fresh database source for requests with
a minimum version requirement. The fact log remains authoritative.

## Lag and recovery

Collect group lag and progress by partition, oldest pending fact age, and consumer
rebalances. Alert on payment freshness independently from Kafka offsets. Identify
whether the lag is in the outbox, the broker, the projector or the database.
Roll back a regressed rollout, scale only when useful partitions and database
capacity exist, and replay from committed offsets with idempotent projection.
Use replication and retention sized for the replay window.

## ECS rollout

Run the API, publisher, and consumer as separate services across availability zones.
For the API, target 100% minimum healthy and up to 200% maximum where capacity
allows. Budget connections for both revisions during overlap. Use process liveness
for the container and bounded readiness for the ALB. Enable circuit-breaker rollback
and CloudWatch deployment alarms. Drain connections and use backward-compatible,
expand/contract schema changes. For consumers, stop taking new work on SIGTERM,
finish or roll back the transaction, and commit only processed offsets. Verify
rollout health with synthetic ingestion, 5xx rate and freshness during a bake window.

## Cost decisions

1. Keep a resilient task baseline and schedule extra consumer capacity ahead of
   predictable payment peaks. Scale back after backlog clears.
2. Reduce RDS query I/O and connection overhead with indexes, measured batching and
   bounded pools before increasing instance class or adding replicas. Keep failover
   and peak headroom in the capacity model.
