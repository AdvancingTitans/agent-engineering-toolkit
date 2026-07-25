# Portable Evidence Bundle v1

## 目标

Portable Evidence Bundle 是一个与 Agent、SDK 和运行时无关的证据交换协议。它将调查结果拆分为可验证证据、运行记录观察、反证、冲突、诊断和未知，使审查者无需安装 AET 也能独立形成判断。

协议不授予修改、合并、发布或自动采纳权限，也不把生产者的判断视为最终权威。

## 证据边界

```text
Run Record
    ↓
Observation
    ↓
Evidence Candidate
    ↓
Verified Evidence
    ↓
Portable Claim
    ↓
Reviewer Judgment
```

- `Run Record` 只描述记录中出现的内容。
- `Observation` 必须同时说明已经证明与尚未证明的内容。
- `Evidence Candidate` 在验证前不能进入强证据集合。
- `Verified Evidence` 必须绑定来源、强度、Freshness 和限制。
- `Portable Claim` 是调查结果，不是最终审查结论。
- `Reviewer Judgment` 由消费者独立形成，人类保留行动权。

## 目录布局

```text
evidence-bundle/
├── manifest.json
├── index.json
├── core/
│   ├── claims.jsonl
│   ├── evidence.jsonl
│   └── observations.jsonl
├── archive/
│   ├── sources.jsonl
│   ├── diagnostics.jsonl
│   ├── conflicts.jsonl
│   └── ledger.jsonl
├── blobs/
│   └── sha256-<hash>
├── policy.json
├── consumer-guide.md
└── report.md
```

`manifest.json` 是权威入口，声明协议版本、任务、调查、内容位置和逐文件哈希。`index.json` 提供最小读取路径。`core/` 只包含当前问题直接相关的数据。`archive/` 保存来源、诊断、冲突和调查账本。大内容以原始字节写入 `blobs/`。

`archive/ledger.jsonl` 的每一行必须符合
`schemas/evidence-bundle/v1/ledger-entry.schema.json`。`hypothesis_ref`
使用稳定的 `primary` 或 `competing:<id>` 形式；工具动作必须声明
`tool_name`，且输入、输出和观察引用必须在 Bundle 中闭合。

## 读取顺序

1. 验证 `manifest.json` 的协议名称和版本。
2. 验证 `integrity.file_hashes` 中每个文件的 SHA-256。
3. 读取 `index.json`。
4. 读取 `core/claims.jsonl`、`core/evidence.jsonl` 和 `core/observations.jsonl`。
5. 当 Claim 冲突、证据截断、身份降级或 Freshness 未知时，再读取 `archive/` 和对应 Blob。

消费者不得跳过完整性校验后仍声称 Bundle 已验证。

## Claim 语义

| 状态 | 含义 |
|---|---|
| `supported` | 现有证据直接支持命题，且没有未披露的实质反证 |
| `partially_supported` | 只支持命题的一部分，限制会影响结论范围 |
| `unsupported` | 已完成所需搜索，但现有证据不支持命题 |
| `conflicted` | 支持证据与反证同时存在且尚未解决 |
| `unknown` | 证据、权限、工具、预算或 Freshness 不足以作出判断 |

`unsupported` 不等于命题为假，`unknown` 也不得强化为确定否定。

## Evidence 强度

| 强度 | 含义 |
|---|---|
| `context_only` | Agent 自述、意图或背景，只能用于提出问题 |
| `observed` | 标准化运行记录中出现了相应调用或结果 |
| `corroborated` | 运行记录与独立 Git、文件、Artifact 或回执相互印证 |
| `reproduced` | 命令结果由 AET 确定性 Proof Runtime 实际执行并记录，且保留工作区绑定 |

运行记录中的工具输出最高默认只能是 `observed`。只有确定性 Proof Runtime 的实际执行回执才能成为 `reproduced`；历史回执能否用于当前结论，还必须由 Freshness 单独决定。

## Freshness

| 状态 | 对消费的影响 |
|---|---|
| `current` | 证据绑定仍与当前工作区和环境相符 |
| `relevant_files_changed` | 历史事实保留，但不能证明当前相关文件状态 |
| `workspace_changed` | 工作区绑定发生变化，需要重新评估适用性 |
| `environment_changed` | 运行环境发生变化，需要重新执行或说明限制 |
| `unknown` | 无法完成可靠时效检查 |

Freshness 只能改变当前适用性，不能改写历史命令的 argv、退出码或输出哈希。

## Observation 规则

每个 Observation 必须包含：

- `proves`：运行记录本身能够支持的最小命题。
- `does_not_prove`：容易被消费者错误推断、但记录不能证明的命题。
- `source_refs`：稳定来源引用。
- `limitations`：截断、身份降级、缺失时间或其他限制。

Reasoning 记录只能用于提出假设、定位调查方向或识别矛盾，不能直接证明工程事实。

## Counter-evidence 与 Conflict

Claim 的 `counter_evidence_refs` 是语义组成部分。删除、隐藏或改写其中任一相关反证都会使 Bundle 验证失败。

冲突通过独立记录表达。生产者不得通过覆盖或删除旧证据来“解决”冲突。补充调查必须创建新的 Investigation 和派生 Bundle。

## Blob 与截断视图

模型读取视图可以截断，但完整证据内容必须保存在 Blob 中并通过 SHA-256 寻址。截断 Evidence 必须声明：

- `truncated: true`
- `original_bytes`
- `blob_ref`
- 完整内容的 `content_hash`

如果完整 Blob 缺失或哈希不匹配，依赖该内容的结论不能作为完整证据通过验证。

## 完整性与规范序列化

- 编码：UTF-8。
- JSON 对象键：字典序。
- JSON 数组：保持语义顺序。
- 时间：ISO 8601 UTC。
- 哈希：SHA-256 小写十六进制。
- Blob：对原始字节计算哈希。
- JSONL：每行一个完整 JSON 对象。
- 对象不得包含未声明的协议字段。

Bundle 的 `content_hash` 对完整 Manifest 进行规范哈希，仅在计算时把
`bundle.content_hash` 自身替换为 64 个 `0`。因此任务、Commit、调查状态、
内容路径和逐文件哈希图都被绑定，同时避免自引用。

## 隐私与脱敏

- 默认不导出隐藏推理。
- 默认脱敏 Token、Cookie、密钥和不必要的用户绝对路径。
- 诊断消息不得包含敏感原文。
- 脱敏内容必须记录派生内容哈希。
- Host 可通过 Policy 禁止导出完整工具输出或 Blob。

## 兼容策略

- `1.x` 可在明确声明的 `extensions` 命名空间内新增可选字段，但不能改变既有字段语义。
- 删除字段、改变字段语义或引用关系需要新主版本。
- 消费者可以忽略 `extensions` 中的未知可选字段；v1 核心对象保持严格字段集合。
- 未知枚举值不得静默映射，必须报告 `unsupported_semantics`。

## 通用消费规则

审查者应：

1. 为事实结论引用 Claim 和 Evidence ID。
2. 区分 Observation、`corroborated` 和 `reproduced`。
3. 在使用历史证据前检查 Freshness。
4. 保留 `conflicted` 和 `unknown`。
5. 披露相关反证。
6. 不把缺失证据解释为事情没有发生。
7. 在证据不足时请求补充调查。

这些规则是开放协议指导，不是模型行为保证。宿主可以选择使用 Portable Review Result 与独立引用验证器检查消费结果。
