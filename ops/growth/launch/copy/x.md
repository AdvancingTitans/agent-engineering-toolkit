# X launch briefs

Owner: `HUMAN_MAINTAINER`

Status: `MANUAL_NOT_STARTED`

Stop Rule: Pause after two qualified posts below 1% Star/unique with no
technical interaction or external use case.

## Angle 1 — the question

Use a 20-second terminal recording. Open with: “Your coding Agent says tests
passed. Did it test this code—or the version before the last edit?” Show only
the exact command and three states. Link the exact release.

## Angle 2 — the semantics

Explain that AET preserves the historical `PASS`; it changes current
applicability to `RELEVANT_FILES_CHANGED`. Avoid “AI tests are fake” or a list
of every product surface.

## Angle 3 — the handoff

Show the proof JSON moving from one Agent workflow to a reviewer, with no AET
telemetry or model dependency. State that a Bundle remains readable without
AET installed.

## Recording script

```text
run exact released uvx command
pause on PASS
pause on EXACT_MATCH
highlight RELEVANT_FILES_CHANGED
end on the boundary sentence, not a Star request
```
