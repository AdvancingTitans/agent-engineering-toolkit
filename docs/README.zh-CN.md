# Agent Engineering Toolkit（AET）

[![CI](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AdvancingTitans/agent-engineering-toolkit?display_name=tag&sort=semver)](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](../LICENSE)
[![English](https://img.shields.io/badge/docs-English-blue)](../README.md)

**[English](../README.md) · [简体中文](README.zh-CN.md)**

> **面向 Agent 工程仓库的 evidence-driven 控制平面。**

Agent 可以写代码、调用工具，也可以声称“已经完成”。AET 负责回答更难、
也更接近生产的问题：**到底发生了什么、现在能声明什么、什么仍然未知、哪里失败了、
哪些治理资产允许演进，以及谁有权批准变化。**

AET 位于外部 Agent Runtime 与生产信任之间。它把命令、Diff、Artifact、指令、工作区状态
与人工 Intent 转化为哈希绑定的工程证据；把已确认失败沉淀为受限质量资产；再通过
Candidate 无权修改的 evaluator 验证治理资产的改进。

```text
外部执行 → Evidence IR → 确定性 Quality → 受限 Evolution
         → 独立 Gates → 人工 Adoption
```

它不是又一个 Agent Runtime，也不是只会出分的评测看板。它是一层让 Agent 工作在发布前
**可检查**、让治理能力在不把裁判权交给优化器的前提下**可演进**的工程系统。

## 先看结果，而不是口号

v1.9 Release 使用真实 Codex CLI `0.144.1`，在三个字节隔离的 Suite 上执行发布门禁；
每套均包含 6 组 baseline/candidate 配对 rollout。

| 真实宿主发布门禁 | Baseline | 受限 Candidate | 绝对提升 | Infra 失败 | 精确配对 p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Core | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| Validation | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| Held-out | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| **连续成功** | **0 / 18** | **18 / 18** | **+100 pp** | **0** | — |

18 次 Candidate 成功运行全部只执行了 1 条授权的 `aet trace` 命令；Candidate 被限制在
676 字符的 edit budget 内，无权修改 Task Suite 或 evaluator，最终 Adoption 仍属于人。

这是一项 AET 自身 Release Gate 案例，不是用一个小任务宣称模型普遍优于其他产品。
它验证的是 AET 最核心的工程能力：**治理资产可以在隔离、统计、provenance 绑定且人工受控的
评估中，稳定改善真实 Agent 行为。** 可复现 Suite 与 Producer 位于
[`eval/real-agent`](../eval/real-agent) 和
[真实宿主 Workflow](../.github/workflows/real-host-gate.yml)。

## AET 为什么不同

很多 Agent 质量方案从 transcript 或分数开始；AET 从信任边界开始。

| 工程问题 | 常见捷径 | AET 的契约 |
| --- | --- | --- |
| Proof | Agent 说“测试通过”。 | `trace` 记录精确 argv、退出码、日志、声明 Artifact 与 proof binding。 |
| Freshness | 一份历史通过日志被永久当成有效。 | “命令曾成功”与“当前工作区仍匹配”是两个独立事实。 |
| 不确定性 | 缺失证据被压进一个分数。 | `UNKNOWN` 是一等状态，也是阻断发布的验证缺口。 |
| Diagnosis | 让模型猜根因。 | 显式 Policy 把问题现象映射到受限 owner/repair surface，且不改写源状态。 |
| Improvement | Candidate 改 Prompt 后自己给自己打分。 | Candidate 写入面、Evaluator、Held-out、证据语义和 Adoption 权限彼此隔离。 |
| Reliability | 跑通一次就算成功。 | 同时报告 any-success、all-success、Wilson 95% 与配对精确 McNemar。 |
| Privacy | 默认把原始对话变成数据湖。 | 原始 rollout 保持私有；只有去标识的 Evidence Only 记录可以流转。 |
| Authority | Optimizer 通过后自动部署自己。 | Gate → Stage → 人工审阅 → 显式 `adopt --yes`；绝不自动提交、推送或发布。 |

这是一种有意设计的非对称权限：Agent 可以执行工作，但不能给自己授予 Evidence、重定义
`PASS`、替换 evaluator，或批准自己的 Adoption。

## 架构

![AET evidence-driven Agent 工程控制平面](assets/aet-architecture-zh-cn.png)

可离线编辑的源文件：[中文 HTML](assets/aet-architecture-zh-cn.html) ·
[English HTML](assets/aet-architecture-en.html)。

整个系统由五个协作阶段和一个不可妥协的人工权限边界组成：

1. **Evidence Plane——采集事实。** `audit`、`review`、`trace`、`context`、
   `decision`、`run` 与 `evolve` 只记录语义窄、哈希绑定的事实。只有 `trace`
   执行命令，而且只执行 `--` 后的 argv。
2. **Deterministic Quality——解释，但不猜。** `quality diagnose` 使用显式本地映射；
   `quality promote` 只能把已确认、已脱敏的问题暂存为 validation-only 回归候选。
3. **Bounded Evolution——在 Constitution 内提案。** Evidence Only Pattern 经过一个
   已注册 Target Adapter 和受限 Patch IR；Evaluator 与 Evidence 语义保持在写入面外。
4. **Independent Gates——证明行为，而不是检查文案。** 根据 Target 使用 Core、
   Validation、Held-out、Adversarial、Policy 或 Shadow Suite；真实宿主评测必须显式启用并重复运行。
5. **Human Adoption——保留最终权限。** Gate 通过只生成可审阅 Stage；Adoption 会重新校验
   baseline hash，要求人工显式授权，并把结果写入 Decision Ledger。

系统终点不只是报告，而是一组持续增厚的工程资产：Evidence Pack、Regression Candidate、
Diagnosis Record、Gate/Shadow Evidence、Rejection Memory、Context Manifest、Run Manifest
与 Decision Ledger。

## 产品能力面

从能回答问题的最小能力面开始。

| 需要回答的问题 | 命令 | 能建立的事实 |
| --- | --- | --- |
| Agent 指令和 Skill 在结构上是否可用？ | `aet audit` | 确定性 Finding、来源证据、RulePack Identity 与 Remediation。 |
| Diff 是否在人工批准的变更契约内？ | `aet review` | Intent、路径预算、Proof 声明与可选 Review Policy。 |
| 这条精确 Proof 命令是否运行并生成该 Artifact？ | `aet trace -- <argv>` | 命令、退出状态、日志、Artifact、脱敏与工作区 Snapshot。 |
| 证据能否随 Handoff 流转？ | `aet evidence pack` | Portable Evidence Pack 与可选静态 Viewer。 |
| Proof 之后仓库是否变化？ | `aet run verify` | Fresh、Stale 或显式 Unknown 的生命周期状态。 |
| 哪些 Context 与 Decision 真的被记录？ | `aet context`、`aet decision` | 哈希绑定 Manifest 与有来源的项目记忆。 |
| 仓库为什么演进为当前状态？ | `aet evolve` | 有引用的本地/显式远端考古，不虚构作者意图。 |
| 哪条受限路径对应结构化失败？ | `aet quality diagnose` | 保留状态的 Owner/Action/Repair Mapping 与人工复核路由。 |
| 已确认失败能否变成回归资产？ | `aet quality promote` | Validation-only Task v2 暂存包，不写生产资产。 |
| 反复失败能否安全改进治理资产？ | `aet learn` | Evidence Only 挖掘、目标专属 Replay/Gate、Stage 与人工 Adoption。 |

## 快速开始：可信交付

安装当前 Release：

```bash
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.9.0/agent_engineering_toolkit-1.9.0-py3-none-any.whl
aet --version
```

创建可审阅契约、审计指令、检查 Diff，再通过 Trace 执行声明的 Proof：

```bash
aet init --output aet.toml

aet audit . --strict --format json \
  --output .aet/evidence/audit.json

aet review . --base main --intent aet.intent.json --format json \
  --output .aet/evidence/review.json

aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/pytest.txt \
  --output .aet/evidence/trace.json \
  -- python -m pytest -q

aet evidence pack \
  --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
```

`audit` 与 `review` 永远不会执行声明的 Proof。Audit 即使发现真实问题，也会先写报告再以
非零退出；应先读 Finding。Trace 必须显式启用，会拒绝不安全 Artifact 路径，独立脱敏声明的
UTF-8 Artifact，并把“子命令成功”和“Artifact 验证缺口”作为两个事实保存。

## 从 Badcase 到 Regression Asset

Quality 必须先确定，再生成：

```bash
aet quality diagnose \
  --report .aet/evidence/failure.json \
  --policy quality-mapping.json \
  --output .aet/quality/diagnosis.json

aet quality promote \
  --badcase confirmed-badcase.json \
  --diagnosis .aet/quality/diagnosis.json \
  --policy quality-mapping.json \
  --output .aet/quality/staged-regressions
```

Diagnosis 是显式 Policy Lookup，不是语义 RCA。Promotion 有意保持狭窄：样本必须已确认、
可复现、已脱敏、有代表性且不重复。它只写入 content-addressed validation candidate 与
provenance sidecar，不会修改生产 Skill、正式 Suite、工单或 Prompt。

## Evidence-Gated Evolution

AET 当前可以演进六类已注册治理资产：

| Target | Candidate 写入面 | Evaluator | 额外刹车 |
| --- | --- | --- | --- |
| Skill | 带标记的 editable block | 静态契约或真实 Codex/Claude 行为 | 配对统计 + 人工 Adoption |
| Audit Rule | 声明式、不可执行 Detector 选择 | Core / Validation / Held-out / Adversarial Fixture | Adoption-grade 多仓库 Shadow |
| Audit Profile | 单调配置 | 目标专属 Policy Suite | 不能禁用 Rule 或降低 Severity |
| Review Policy | 受限 JSON Patch | Review Policy Suite | 不能扩大 Scope 或删除 Proof |
| Trace Validator | 白名单 Validator Policy | Validator Suite | 不能削弱 Evidence 语义 |
| Triage Policy | 排序 Policy | Triage Suite | 可以重排，不能隐藏或改写 Finding |

标准闭环被显式拆分：

```bash
aet learn harvest --evidence .aet/evidence \
  --output .aet/learn/experiences.json
aet learn mine --experiences .aet/learn/experiences.json \
  --target-type skill --output .aet/learn/patterns.json
aet learn propose --engine rules --patterns .aet/learn/patterns.json \
  --target skills/agent-engineering-toolkit/SKILL.md \
  --output .aet/learn/candidates/CAND-001

aet learn gate --candidate .aet/learn/candidates/CAND-001 \
  --core eval/core --validation eval/validation --held-out eval/held-out \
  --output .aet/learn/gates/CAND-001.json

aet learn stage --candidate .aet/learn/candidates/CAND-001 \
  --gate .aet/learn/gates/CAND-001.json \
  --output .aet/learn/staged
```

`stage` 不等于 Adoption。`adopt --yes` 会重新校验不可变字节与当前 Target Hash。AET 不会
自我调度、上传 Transcript、创建工单、Commit、Push 或发布 Release。

### 真实宿主评测

Static Replay 只检查文档契约，绝不会被描述成真实 Agent 行为。需要行为证据时必须显式指定 Runner：

```bash
aet learn runner list

aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/real-agent/core --runner codex --rollouts 3 \
  --runner-config runner.json \
  --output .aet/learn/replays/CAND-001

aet learn gate --candidate .aet/learn/candidates/CAND-001 \
  --core eval/real-agent/core \
  --validation eval/real-agent/validation \
  --held-out eval/real-agent/held-out \
  --runner codex --rollouts 6 --statistics-profile adoptable \
  --runner-config runner.json \
  --output .aet/learn/gates/CAND-001.json
```

宿主启动、认证失败、Timeout、空 Structured Event 或不支持的隔离能力必须保持
`INFRASTRUCTURE_ERROR`、`UNKNOWN` 或 `INCONCLUSIVE`，绝不会变成 Candidate PASS。
Raw Output 与 Normalized Event 保持在私有 Rollout 目录；只有派生的 Evidence Only
Phenomenon、Score 和 Hash 可以导出。

## AET 在工具链中的位置

AET 与现有工具协作，而不是假装替代它们。

| 工具类别 | 它负责什么 | AET 负责什么 |
| --- | --- | --- |
| Codex、Claude Code、Copilot 等 Runtime | 在仓库中规划并执行工作 | 围绕 Runtime 交付声明建立 Evidence 与 Authority |
| Test、CI、Lint、安全扫描器 | 各自领域的检查 | 绑定检查的精确执行、Artifact、Intent 与 Freshness |
| LangSmith、Braintrust、DeepEval、可观测平台 | 广泛实验、Trace 与 Fleet Analytics | 本地工程证据语义，以及受限治理资产的 Adoption |
| OPA 等 Policy Engine | 通用、预定义 Policy 执行 | AET 专属单调 Policy 与 Evidence-Gated Evolution |
| Skill 创作与优化系统 | 创建或训练 Skill 内容 | 证明在用行为，并约束什么可以评估、Stage 和 Adopt |
| 工单与业务看板 | 运营流转和线上结果 | 可供其消费的结构化本地 Evidence |

当 Coding Agent Handoff 不能只靠“看起来不错”、当 `FAIL` 与 `UNKNOWN` 必须保持不同、
或当反复失败需要改进治理资产却不能让 Candidate 掌控自己的 Evaluator 时，选择 AET。

不要把 AET 当作 Agent Runtime、通用 Benchmark、LLM Judge 中心、自动语义 RCA/Evidence
Graph、聚类平台、Skill Quality YAML 标准、托管 Transcript 服务、业务看板或自动发布 Bot。

## 安全与信任边界

- **只有 Trace 执行。** `audit`、`review`、Quality Diagnosis、Evidence Pack 与
  Deterministic Replay 都不会执行 Proof 命令。
- **Trace Evidence 会被独立校验。** Scorer 绑定 trusted wrapper、outer child argv、
  Trace argv、Intent Proof Command、Artifact、Log、Redaction Rule 与前后 Snapshot；
  长得像命令的文本不是 Proof。
- **Fixture Copy 不跟随链接。** Nested Symlink、Special File、Outside-root Source 与
  Copy 后 Hash Drift 都会被拒绝。
- **环境权限必须显式声明。** Task 指定允许继承的环境变量；Process Runner 对 `HOME`
  还要求 `inherit_home: true`。允许继承不等于允许导出。
- **Network Posture 必须诚实。** 无法提供 OS-level Deny 的 Runner 报告 `PARTIAL`；
  `enforced-deny` Task 会在执行前失败。
- **Candidate 权限受限。** Evaluator Code、Held-out Case、Constitution、Evidence State
  与 Human Adoption 都不在 Candidate 写入面内。

这些约束降低 Candidate 对判定的影响，但不会声称存在“不可能被利用”的 evaluator、完美 Sandbox，
也不会因为一份指令被发现就断言模型真正理解了它。

## Portable Skill 与仓库考古

工具中立的 canonical Skill 位于
[`skills/agent-engineering-toolkit`](../skills/agent-engineering-toolkit)。Wheel 只包含 CLI，
不携带 Skill 资源。请从源码 Checkout 复制完整目录，而不是只复制 `SKILL.md`：

```bash
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
cp -R skills/agent-engineering-toolkit ~/.codex/skills/
aet audit ~/.codex --format json --output ~/.aet/evidence/codex-audit.json
```

对于有来源的项目历史，`aet evolve plan/collect/build/report` 默认只收集本地 Git 与文档；
只有显式传入 `--remote github` 才访问 GitHub。缺失远端证据保持 `UNKNOWN`，AET 不会仅凭
Commit 文本虚构作者意图。

## 验证

Release 自带可运行的验证路径：

```bash
uv run --with pytest python -m pytest -q
uv run --with pytest python -m pytest tests/test_business_quality_flows.py -q
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  aet audit . --strict --format json --output .aet/evidence/release-audit.json
uv build
uv run --isolated --with dist/agent_engineering_toolkit-1.9.0-py3-none-any.whl \
  aet --version
```

详细契约参见 [CHANGELOG](../CHANGELOG.md)、
[Evolution Boundary](evolution-boundary.md) 与
[v1.9 实施方案](superpowers/plans/2026-07-13-v1-9-quality-loop.md)。

## 贡献

欢迎 Issue 与 Pull Request。请保留 AET 的定义性约束：确定性检查先于模型判断、显式
`UNKNOWN`、Candidate 与 Evaluator 隔离、Raw Evidence 私有、Target-specific Gate，
以及人对 Adoption 的最终权限。

项目采用 [MIT License](../LICENSE)。
