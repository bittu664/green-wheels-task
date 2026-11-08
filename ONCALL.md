# On-call for four engineers

Rotate weekly with one primary and one secondary. For engineers A–D, use A/B,
B/C, C/D, D/A (primary/secondary). Adjust for time off and distribute weekend duty.
Nairobi and Pune overlap in working hours, so plan explicit overnight coverage and
relief after a disruptive incident.

Handoff on Monday at 11:00 Nairobi and 13:30 Pune. Review active incidents, affected
countries, error-budget burn, risky releases, and any disabled or noisy alert. The
incoming primary acknowledges ownership in the shared channel.

| Tier | Threshold and response |
|---|---|
| Primary | Acknowledge critical pages within five minutes, declare severity and start mitigation. |
| Secondary | Page after five minutes without acknowledgment or ten minutes without containment. Join immediately for suspected payment integrity problems. |
| Specialist and Fleet Ops | Bring in the relevant database, Kafka or platform owner when the first diagnosis identifies that dependency. Notify Fleet Ops when payments, assignments, or driver income may be affected. |
| Incident commander | Assign an engineer to coordinate if multiple responders are active or impact extends across markets. Send updates every 15 minutes during a critical incident. |

At 50% consumption of any rolling 30-day error budget, review risky lease changes.
On active fast burn or budget exhaustion, pause feature releases to the affected
service. Allow rollback, reliability, and urgent security changes. Resume after
mitigation and service-owner review. Track remediation and assign an owner.

- Days 1–30. Log each page, its trigger, whether intervention was necessary, and
  time to acknowledge. Fix broken runbooks and duplicate pages.
- Days 31–60. Move non-urgent alerts to work-hours Slack or tickets. Tune windows,
  validate grouping, and run both incident drills.
- Days 61–90. Review overnight page rate, actionable fraction, recurrence, and
  time to recover. Remove alerts without an action after confirming coverage.
  Add an acknowledgment-capable paging destination for critical events.
