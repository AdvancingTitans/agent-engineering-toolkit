# Agent Task

Candidate status: `PROPOSED`

## Problem
Claim is not supported by evidence

## Evidence
ev-empty-result-regression
Finding refs: claim-empty-result-is-grounded

## Allowed Scope
- `examples/evidence-grounded-improvement/sample_project/tool_result.py`

## Forbidden Scope
- `tests/evals/**`
- `eval/**`
- `grader/**`
- `fixtures/**`
- `.aet/**`
- Do not convert an empty result into a factual claim.

## Verification
- `python examples/evidence-grounded-improvement/sample_project/test_tool_result.py`

## Stop Conditions
- Stop if any Evidence or Finding reference is missing.
- Stop before changing a protected path.
- Stop if verification cannot produce valid Proof.
