# Growth operations

These files support maintainer-run activation and distribution experiments.
They are not part of the AET runtime, collect no product telemetry, and grant
no authority to publish, post, change repository settings, or contact people.

Actual snapshots belong under ignored `.aet/growth/metrics/` or workflow
artifacts. Only schemas, examples, methods, and manual checklists are tracked.

## Phase 5 operating loop

After a human publishes the exact v1.18 artifact:

1. Capture T+72h, T+7d, and T+30d aggregate snapshots.
2. Compare only `KNOWN` values with `scripts/growth/evaluate.py`.
3. Turn one real repository problem into reproducible Evidence.
4. Have a maintainer explain what it proves and does not prove.
5. Prefer an external user case over another first-party feature article.
6. Open 3–5 fixture-backed Good First Issues only when support capacity exists.

Stop a channel after two qualified events below 1% Star/unique with no
high-quality interaction. When visits are high but demo use is low, rewrite the
landing path instead of adding core features. When support load exceeds
capacity, pause new distribution.

## Phase 6 trigger

Homebrew, Scoop, Nix, broader IDE/CI integrations, attestations, conferences,
and enterprise templates remain `DEFERRED_WITH_REASON` until Phase 1–5 produce
real repeat use, external cases, and enough maintenance capacity. Current local
implementation does not satisfy that trigger and must not report Phase 6 as
completed.
