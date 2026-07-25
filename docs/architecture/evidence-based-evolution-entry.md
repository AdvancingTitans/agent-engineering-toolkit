# 基于证据的自进化入口

本入口对应实施计划第 13 节 Phase 7。它只把已验证的 Portable Evidence
Bundle 与 Portable Review Result 转换为 `OptimizationCandidate`，不执行聚类、
修改、采用或发布。

## 输入边界

调用 `aet.optimization.build_optimization_candidate` 时，每项
`supporting_inputs` 必须提供：

- `bundle_path`：Portable Evidence Bundle 目录；
- `review`：Portable Review Result 对象或 JSON 文件；
- `review_refs`：本候选实际引用的 Review Conclusion ID；
- `run_refs`：可选的 `run_record` Source ID。

入口首先调用现有 Bundle 与 Review Validator。无效哈希、无效引用、缺失反证、
过期证据越级或未知字段会沿用现有 fail-closed 行为。公开候选中的引用使用以下
确定性定位格式，避免不同 Bundle 内的局部 ID 冲突：

```text
<bundle-id>#review-conclusion:<conclusion-id>
<bundle-id>#run-record:<source-id>
```

## 资格门禁

候选必须满足以下二者之一：

1. 已验证支持来自至少两个不同的 `task_id`；
2. 单个任务提供显式 `deterministic_failure`，其严重程度为 `high` 或
   `critical`。

第二条入口还必须同时满足：

- 引用的 Review Conclusion 已被选为候选支持；
- Review disposition 为 `request_change`；
- Claim basis 为 `deterministic` 或 `reproduced`；
- Evidence 同时被 Claim 与 Review 引用；
- Evidence 不是 `run_observation`；
- Evidence 强度为 `corroborated` 或 `reproduced`；
- Evidence freshness 为 `current`。

这条门禁只允许生成评测候选，不能把一次失败直接转化为规则。

## 输出与禁止行为

输出严格遵循 `schemas/optimization/v1/candidate.schema.json`，并始终包含：

```json
{
  "evaluationRequired": true
}
```

入口只返回内存中的结构化对象。它不提供 CLI，不自动扫描或聚类历史记录，不写入
Skill、Source Adapter、调查策略或其他生产资产，不自动运行评测，不覆盖基线，不
自动采用，也不发布结果。调用方若要继续推进，必须在隔离 Fixture 中保留基线并
完成人工审查与采用。
