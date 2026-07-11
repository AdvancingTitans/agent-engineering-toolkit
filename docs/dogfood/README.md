# Phase 0 dogfood baseline

These reports were generated on 2026-07-11 from read-only shallow clones. The
clones remain under ignored `work/dogfood/`; the committed Markdown and JSON
files preserve the evidence snapshot.

| Repository | Commit | Assets | FAIL | UNKNOWN |
|---|---|---:|---:|---:|
| stock-analysis | `e875974992e8a5258df9723ead115390efecf5a1` | 1 | 0 | 0 |
| pain-miner | `ddf3ce20a1bc0cfbd04b79ac76c8e713b6ff0fda` | 1 | 0 | 0 |
| cli-creator-skill | `418e941607a53be95921edbbb8e2196411b7893d` | 1 | 0 | 0 |

The first stock-analysis pass incorrectly treated generated Evidence Pack names
as broken paths and missed Chinese verification language. The final reports
were regenerated after both corrections; this is why the committed reports are
the canonical Phase 0 baseline.
