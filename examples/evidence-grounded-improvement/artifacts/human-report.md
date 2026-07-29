# Human Improvement Report

## IMP-001 — Claim is not supported by evidence

### 一句话结论
An empty tool result is evidence-grounded and may be reported as “No security issues were found.”

### 为什么发现
Finding: claim-empty-result-is-grounded; category: `unsupported_claim`; confidence: `high`.

### 证据
ev-empty-result-regression

### 影响
Priority: `P1_HIGH`. The recorded behavior cannot be treated as safely improved yet.

### 建议目标
Prevent unsupported facts from being emitted as evidence-grounded claims.

### 禁止修改
tests/evals/**; eval/**; grader/**; fixtures/**; .aet/**; Do not convert an empty result into a factual claim.

### 验证方式
python examples/evidence-grounded-improvement/sample_project/test_tool_result.py

### 未知项
No production repository behavior is inferred from this fixture.; The root cause is bounded to the sample adapter.
