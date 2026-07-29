# AET vs observability

Observability platforms explain broad runtime behavior through logs, metrics,
and traces across deployed systems. AET focuses on local engineering evidence
for a bounded coding task.

AET records which command ran, which source and artifacts it covered, how that
evidence relates to an intent contract, and whether it still applies. It is not
an application monitoring backend, telemetry collector, or distributed trace
store.

The two are complementary: production evidence can motivate a task, while AET
helps keep the resulting code change and verification handoff reviewable.
