# Greenwheels Fleet Lease Reliability

A runnable SRE exercise for lease status and payment facts. Each driver represents one
lease aggregate in this simulation. The status rules and payment-cycle counter are illustrative.

## Run locally

Requires Docker with Compose v2. Use the seeded local credentials only in this stack.

```sh
docker compose up --build -d
curl -fsS localhost:8000/health
event_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
payload="{\"event_id\":\"$event_id\",\"driver_id\":\"demo-1\",\"event_type\":\"payment_made\"}"
curl -fsS -H 'Content-Type: application/json' -d "$payload" localhost:8000/leases/events
curl -fsS -H 'Content-Type: application/json' -d "$payload" localhost:8000/leases/events
curl -fsS localhost:8000/leases/demo-1
curl -fsS localhost:8000/metrics | grep lease_http
```

Retry the read if the projector has not caught up yet. Both submissions should return
the same version. The initial payment cycle should be 1 on a fresh stack. Other facts
are `payment_missed` and `lease_paused`. A different payload with the same event ID
returns 409. Readiness is `/health` and process liveness is `/live`.

Grafana is at http://localhost:3000 with local credentials `admin/admin`. Open
**Greenwheels Fleet Lease**. Prometheus is at http://localhost:9090 and Alertmanager
at http://localhost:9093. Slack delivery is opt-in. Set `SLACK_WEBHOOK_FILE` to an
absolute, container-readable secret path and run
`docker compose -f compose.yaml -f compose.slack.yaml up -d --build`.
The workspace webhook must support the configured destinations. If Slack binds each
webhook to one channel, configure a separate `api_url_file` for each receiver.
Replace `YOUR_ORG/greenwheels-lease` in `monitoring/rules.yml` with the actual runbook
repository before enabling notifications. The default receiver lets you drill locally.

## Validate

```sh
python -m pip install -r requirements-dev.txt
ruff check .
python -m pytest tests/test_unit.py
LEASE_TEST_URL=http://127.0.0.1:8000 python -m pytest tests/test_integration.py
```

The integration test submits and retries a fact, waits for the Kafka projector,
verifies a single state transition, and checks the metric labels. Run the incident
drills in [RUNBOOK.md](RUNBOOK.md). `docker compose down` retains the demo data.
`docker compose down -v` removes it.

## SLO policy

Each target uses a rolling 30-day window. Ratios with zero eligible events are
undefined. No traffic does not count as success. During startup, use the dashboard
with the actual observation period until 30 days of telemetry exists.

| SLI | Good / eligible | Target | Error budget |
|---|---|---|---|
| Ingestion availability | 202, including identical retries, over eligible POST responses. Server errors and 429 are bad. Invalid inputs and conflicts are excluded. | 99.9% | 0.1% |
| Read latency | Eligible GET returns 200 or a legitimate 404 within 300 ms. Server errors and 429 also count against the budget. | 99% | 1% |
| Payment freshness | Unique accepted payment facts reflected in the read model within 30 seconds, divided by all payment facts whose deadline has passed and been evaluated. Pending facts at deadline are bad. | 99.5% | 0.5% |

The evaluator stores the outcome and increments the persistent counters in one
transaction. Evaluator scrape failures are surfaced independently. In production,
track evaluator scoring delay, measure user-facing failures at the ALB or gateway,
and keep edge metrics separate until deduplicated against application counts.
The demo HTTP ratios cover responses observed by FastAPI.

Critical alerts use 14.4× burn over both 5m and 1h. At low traffic a single
failure can trip the ratio if it is visible in both windows. Review that behavior
during the first month. The readiness probe detects hard outages independently.
The Kafka exporter can report a group only after it has offset metadata.

## GitHub Actions and AWS

Configure repository variables `AWS_ROLE_ARN`, `AWS_REGION`, and `ECR_REPOSITORY`.
Provision the ECR repository and an OIDC role scoped to this repository's main branch
with push permissions to that repository. Enable immutable tags if your release
process uses one tag per commit. PRs validate and smoke-test the build. A push to
main publishes the image that passed the ten-second health gate and integration test.

```sh
terraform -chdir=terraform init
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=sandbox.tfplan
terraform -chdir=terraform apply sandbox.tfplan
```

The Terraform module provisions the CloudWatch log group, filters, two alarms and
an SNS topic. Configure ECS `awslogs` to use the output log group and connect the
SNS topic to your operations integration. CloudWatch encrypts log groups by default.
Set `logs_kms_key_arn` for an existing customer-managed key with an appropriate policy.
The stack does not provision ECS, RDS, Kafka or ECR. Use a separate database migration
step and replace the local credentials, plaintext Kafka connection and loopback
deployment assumptions before AWS rollout.

See [RUNBOOK.md](RUNBOOK.md), [ONCALL.md](ONCALL.md), and
[ARCHITECTURE.md](ARCHITECTURE.md).
