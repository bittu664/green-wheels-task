# Greenwheels Fleet Lease On-Call

This rotation covers the Lease API, outbox publisher, Kafka projector, and
PostgreSQL dependency. The primary owns the response when drivers cannot read
their lease, payment events fail, or accepted payments stop updating lease status.

## Rotation and handoff

Run two continuous weekly PagerDuty schedules for four engineers. Set the handoff
to Monday at **08:00 UTC / 11:00 Nairobi / 13:30 Pune**. Repeat the cycle every four weeks.

| Week | Greenwheels Primary | Greenwheels Secondary |
|---|---|---|
| 1 | Engineer A | Engineer B |
| 2 | Engineer B | Engineer C |
| 3 | Engineer C | Engineer D |
| 4 | Engineer D | Engineer A |

Replace A–D with the team's actual PagerDuty users. Check both schedules for gaps
and overlapping assignments before a holiday or leave. Use a schedule override
with a named replacement. Arrange coverage for an engineer who needs rest after
a disruptive overnight incident.

At handoff, review active incidents and affected markets, the three SLOs and their
remaining budgets, planned releases, active silences with expiry times, and open
follow-ups. The incoming primary confirms ownership in the team channel. For an
active incident, transfer ownership explicitly in PagerDuty and the incident notes.

## PagerDuty configuration

1. Create the **Greenwheels Primary** and **Greenwheels Secondary** schedules using
   the rotation above. Have every engineer test mobile push and a backup contact method.
2. Create the **Greenwheels Fleet Lease** escalation policy and configure these levels.
3. Create the **Greenwheels Fleet Lease Production** service, attach that policy, and
   add an **Events API v2** integration. Configure high urgency for its critical pages.
4. Create a separate test service with a test escalation policy for local drills.
   Use its integration key for Docker Compose.

| Tier | Trigger | Response |
|---|---|---|
| Primary | A critical incident opens | Acknowledge within five minutes, assess driver impact, and begin mitigation. |
| Secondary | No acknowledgment after five minutes | PagerDuty escalates. If the primary has acknowledged but impact remains uncontained at ten minutes, the primary requests the secondary manually. |
| Duty manager or designated lead | A further ten minutes without acknowledgment at tier 2 | PagerDuty escalates to the named lead. Confirm this person and their backup before enabling production paging. |
| Specialist and Fleet Ops | Suspected missing or incorrectly applied payments, or a confirmed dependency failure | Bring in the relevant database, Kafka, or platform owner. Involve Fleet Ops when payment status, assignments, or driver income may be affected. Suspected payment integrity issues warrant immediate secondary involvement. |

Acknowledging an incident stops automatic escalation. The responder retains
ownership until they explicitly transfer it or resolve the incident. For critical
incidents with multiple responders or markets affected, assign an incident
commander and post updates every 15 minutes. Track the start time, impact, actions,
and recovery evidence in the incident record.

## Alert routing

Prometheus evaluates the rules and sends alerts to Alertmanager. Alertmanager
routes critical alerts to PagerDuty and warnings to Slack. Group notifications by
service, alert name, and environment when that label is present. Verify that
production and test use different PagerDuty integration keys.

| Alert | Destination | First action |
|---|---|---|
| LeaseServiceUnavailable | PagerDuty | Check readiness, API logs, and PostgreSQL connectivity. |
| LeaseIngestionHighErrorRate | PagerDuty | Check recent changes and database pool timeouts. |
| LeaseReadLatencyFastBurn | PagerDuty | Compare read latency with database waits and query latency. |
| LeaseFreshnessFastBurn | PagerDuty | Compare outbox age, Kafka lag, and projector progress. |
| LeaseProjectionBacklog | Slack | Find the oldest pending payment and identify the stalled stage. |
| LeaseMonitoringMissing | Slack | Check scrape targets and verify service health separately. |

In `monitoring/alertmanager.slack.yml`, route `severity="critical"` to the
PagerDuty receiver and leave the Slack receiver as the default. Mount the
integration key read-only from `secrets/pagerduty-routing-key` in
`compose.slack.yaml` and reference the container path with `routing_key_file`.
Enable `send_resolved` so Alertmanager sends recovery events. Keep the key outside
Git. Use the diagnosis and recovery steps in [RUNBOOK.md](RUNBOOK.md).

## Release gates

Evaluate the rolling 30-day error budgets defined in [README.md](README.md)
before releasing a lease feature. This is a release decision for the on-call
engineer and service owner.

| Budget state | Release decision |
|---|---|
| Under 50% consumed and no active fast burn | Proceed through the usual release checks. |
| At least 50% consumed | Review risky changes with the service owner before release. |
| Active fast burn or exhausted budget | Pause feature releases for the affected service. Allow rollback, reliability remediation, and urgent security fixes. |

Resume feature releases after recovery is verified, fast burn has stopped, and
the service owner has reviewed the remaining budget and any exception. Assign
each remediation an owner and due date.

## Test the setup

1. Confirm the Compose stack uses the PagerDuty test integration key and that
   the scheduled test responders know the drill is starting.
2. Run `docker compose stop api`. In Prometheus, verify that
   `LeaseServiceUnavailable` moves from Pending to Firing after two minutes of
   continuous probe failures, plus evaluation and notification time.
3. Verify the page reaches the primary. To exercise escalation, wait five minutes
   without acknowledgment and confirm the secondary receives it. Acknowledge the incident.
4. Run `docker compose start api` and check `curl -fsS http://localhost:8000/health`.
   Verify the alert clears and PagerDuty resolves the incident. Record the page,
   acknowledgment, escalation, and recovery times.
5. Run the payment backlog and database pool drills in [RUNBOOK.md](RUNBOOK.md).
   Confirm each alert reaches its intended destination and the responder can
   follow the runbook.

## First 90 days

- **Days 1–30.** Review every page at handoff. Record whether it required immediate
  action, time to acknowledge, and whether the runbook helped. Fix routing gaps
  and duplicate pages.
- **Days 31–60.** Move non-urgent signals to work-hours Slack or tickets, tune
  noisy thresholds against incident evidence, and rehearse escalation and recovery.
- **Days 61–90.** Review actionable-page percentage, overnight page count, median
  acknowledgment and recovery times, and repeated incident causes. Assign owners
  to recurring causes and verify alert coverage before removing redundant pages.