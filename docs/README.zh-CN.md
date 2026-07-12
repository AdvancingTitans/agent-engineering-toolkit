# Agent Engineering Toolkit（AET）

[![CI](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AdvancingTitans/agent-engineering-toolkit?display_name=tag&sort=semver)](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](../LICENSE)
[![English](https://img.shields.io/badge/docs-English-blue)](../README.md)

**[English](../README.md) · [简体中文](README.zh-CN.md)**

> AET 是 Coding Agent 的工作结果与“可以交付”这一结论之间的本地证据层。

**Agent Engineering Toolkit（AET）** 先让 Coding Agent 的工作可检查，再只在改进本身
有证据时让它演进。它记录 Agent 可见的指令、人工批准的改动边界、显式执行的命令、产物
与验证缺口。这些记录既可以随一次交付交接，也可以在失败反复出现时成为受限 Skill 改进
实验的输入。

它用同一套证据模型回答两个问题：

| 问题 | AET 的回答 |
| --- | --- |
| “这次 Agent 交付可以如实说已就绪吗？” | 审计指令、审查人工批准的 diff、Trace 显式 proof，并交接证据。 |
| “反复出现的 Agent 失败能安全改进 Skill 吗？” | 从结构化失败中挖掘模式，只改标记区域，回放 baseline/candidate，经过 Gate 后仍由人采纳。 |

关键在于：AET 不接受 Agent 的自我陈述替代事实。自然语言答复不能替代已记录的命令、产物、
快照或明确的 `UNKNOWN`。

## 为什么要做 AET

Coding Agent 让“改动仓库”变得很便宜，却没有自动回答交付时最关键的问题：*哪些指令在
范围内？命令是否真的跑过？产物是否仍对应当前工作区？哪些已验证，哪些仍未知？*

聊天记录、CI 日志、Prompt 修改和人工清单各自能解决一部分。AET 把它们沉淀为本地、结构化、
哈希绑定的工程事实，并保持语义克制：它今天服务于可信交付，而不是把每次 Agent 对话都当作
训练数据。

## 为什么是 AET

- **证据优先，而非置信度优先。** `UNKNOWN` 永远是验证缺口，不会被折算成通过。
- **最小安全能力面。** `audit`、`review` 只检查；只有 `trace` 执行 `--` 后显式 argv。
- **默认本地。** 证据、Experience Store 与跨项目汇集不要求托管遥测或完整 transcript。
- **proof 与 freshness 分离。** 命令曾成功和工作区后来变更是两个独立事实。
- **改进受约束。** Candidate 受哈希、editable block、独立验证、stage 与人工 adopt 共同限制。
- **可观测真实行为。** 静态 Skill 检查只是 Gate 0；可选 Scripted、Codex、Claude Code runner
  可在隔离任务中用确定性规则评分实际行为。

AET **不是** Agent Runtime、通用自动编程框架、托管监控产品，也不会自动修改生产 Skill。

## 快速开始

```bash
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.7.0/agent_engineering_toolkit-1.7.0-py3-none-any.whl
aet --version

aet init --output aet.toml
aet audit . --strict --format json --output .aet/evidence/audit.json
```

即使发现真实问题，`aet audit` 也会先写出 JSON 再以非零退出码结束。非零表示“证据发现
问题”，不是“没有生成审计 JSON”；应先阅读该产物。

## 选择最小能力面

| 你要确认什么？ | 命令 | 产物 |
| --- | --- | --- |
| 指令、本地引用和 Skill 是否可用？ | `aet audit` | 含位置、证据与修复建议的 Markdown / JSON / SARIF。 |
| diff 是否在人工批准边界内？ | `aet review` | intent、路径预算与 proof 声明报告。 |
| 显式命令是否运行并生成已声明报告？ | `aet trace -- <argv>` | 脱敏执行记录与可选捕获产物。 |
| 如何随 handoff 或 release 交付证据？ | `aet evidence pack` | Portable Evidence Pack 与静态 Viewer。 |
| 审查/测试后工作区是否过期？ | `aet run` | 可选的 append-only 交付生命周期。 |
| 哪些 Context 与决策有本地来源？ | `aet context`、`aet decision` | 哈希绑定的 Context Manifest 与 Decision Ledger。 |
| 仓库为什么这样演进？ | `aet evolve` | 可引用的本地/显式远端演进报告。 |
| 现有 finding 应先修哪个？ | `aet triage` | 可解释排序；绝不改变 finding 原状态。 |
| 重复证据问题能否安全改进 Skill？ | `aet learn` | Evidence Only 经验集、受限候选、Gate 与 staged 副本。 |

## AET 在工具链中的位置

这些工具可以组合使用；下表说明的是各自负责的问题，不是“谁替代谁”的排序。

| 工具类别 | 更适合解决什么 | AET 增加什么，或刻意不做什么 |
| --- | --- | --- |
| Coding Agent Runtime（Codex、Claude Code、Copilot） | 在仓库中规划与执行实际工作。 | AET 不替代 Runtime；它记录 Runtime 的交付结论所需的本地证据。 |
| CI、测试、Lint 与安全扫描 | 用各自的规则检查代码或部署。 | AET 可 Trace 显式检查，并将其产物绑定到 intent、工作区 freshness 与 handoff；不替代检查器。 |
| Skill 工程/治理系统（[Yao Meta Skill](https://github.com/yaojingang/yao-meta-skill)） | 创建、打包、编译、评估并治理可复用的跨平台 Skill 资产。 | AET 聚焦 Coding Agent 交付周围的证据，以及正在使用的 Skill 的受限改进。用 Yao 工程化 Skill 产品；用 AET 为使用该 Skill 的工作提供证据与约束。 |
| Skill 优化器（[SkillOpt](https://github.com/microsoft/SkillOpt)） | 根据有分数的 rollout 与 held-out validation 训练 Skill 文档。 | AET 提供本地工程证据语义：intent 边界、显式命令 proof、artifact、freshness 与人工 adopt；它不是通用 benchmark 优化器。 |
| Transcript 分析 / Agent 可观测平台 | 搜索大规模历史会话、看仪表盘或管理 fleet telemetry。 | AET 默认只保存结构化 Evidence Only 记录，不会摄取无限增长的 transcript 档案。 |

### 适合使用 AET 的场景

- Agent 改完代码后，需要可信 handoff：不仅是“测试通过”，还要有命令、退出码、声明产物、
  批准范围与 freshness。
- 需要保留 **PASS**、**FAIL**、**UNKNOWN** 的差异，而不是把不确定性压缩成一个分数。
- 希望从重复工程失败中改进 Skill，但不允许优化器悄悄放宽安全语义或覆盖正式指令。
- 已经在用 Agent Runtime 和 CI，需要一个本地、可移植的证据层与它们协作。

### AET 不替代什么

- 测试、CI、代码审查或部署安全；
- Agent Runtime 或任务规划器；
- 仅因为文件被发现或被声明“已读”，就断言模型理解/使用了该文件；
- 自动自我修改服务。`propose`、`gate`、`stage`、`adopt` 被有意拆开。

## 架构

```mermaid
flowchart TB
  subgraph delivery["交付证据平面"]
    A["指令与 Skills"] --> B["audit\n静态指令事实"]
    C["人工 intent + Git diff"] --> D["review\n范围与 proof 契约"]
    E["-- 后的显式 argv"] --> F["trace\n已执行 proof + 声明产物"]
    G["仓库 Context 与决策"] --> H["context / decision / evolve\n哈希绑定的本地历史"]
    B --> I["Evidence IR\n状态 + 哈希 + 工作区快照"]
    D --> I
    F --> I
    H --> I
    I --> J["交接\nEvidence Pack / Viewer / Run"]
  end

  subgraph learning["可选的 Evidence-Gated Evolution"]
    I -. "重复的结构化\nEvidence Only 记录" .-> K["harvest + mine\n模式支持度"]
    K --> L["propose\n受限 Patch IR"]
    L --> M["replay\n静态 Gate 0 或隔离宿主 rollout"]
    M --> N["gate\ncore + validation + held-out + 成本"]
    N --> O["stage\n人工审阅副本"]
    O -. "显式 --yes" .-> P["adopt\nSkill + Decision Ledger"]
    N -. "FAIL / INCONCLUSIVE" .-> Q["reject 记录\n负向约束"]
  end

  P --> A
```

学习支路是可选的：AET 不会把每份证据都当成训练数据；静态文本检查不会被描述为已观测
Agent 行为；Gate 通过也不会修改生产 Skill。

## 如何使用 AET

先按工作选择入口，而不是直接启动最重的工作流：

| 如果你需要… | 先使用 | 仅在需要时再增加 |
| --- | --- | --- |
| 检查 Agent 本地指引是否可用 | `aet audit` | 需要发现/已读资产的哈希记录时使用 `context`。 |
| 交付 Agent 生成的改动 | `audit` + `review` + `trace` | 需要可移植交接时使用 `evidence pack`；多生命周期步骤时使用 `run`。 |
| 解释仓库为何形成当前结构 | `aet evolve plan` | 审查收集计划后再执行 `collect/build/report`。 |
| 改进反复出现的 Skill 失败 | `learn harvest` + `mine` | `propose/replay/gate/stage`；只有显式配置时才使用真实宿主 runner。 |

### 配方：有证据的交付

```bash
# audit 与 review 不执行测试。
aet audit . --strict --format json --output .aet/evidence/audit.json
aet review . --base main --intent aet.intent.json --format json --output .aet/evidence/review.json

# 只有 Trace 可执行 -- 后的精确 argv。
aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/junit.xml --output .aet/evidence/trace.json -- \
  python -m unittest discover -s tests -v

aet evidence pack --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
aet evidence viewer --pack .aet/evidence/evidence-pack.json \
  --output .aet/evidence/evidence-viewer.html
```

proof 成功与 freshness 分开表达：命令可能确实成功，但之后工作区变化会让交付变为
STALE。`UNKNOWN` 是待验证缺口，绝不是打折后的通过。

## Evidence-Gated Evolution

v1.7 在 v1.6 的静态合同 Gate 0 之上，加入真实宿主的隔离执行与行为证据：

```text
Evidence Only JSON → inspect → mine → bounded Patch IR → 隔离回放
→ core + validation + held-out Gate → stage → 人工 adopt 或 reject
```

| Phase | 已实现内容 |
| --- | --- |
| 0. Contract | immutable/editable 标记、Candidate 与任务 schema、硬语义门禁。 |
| 1. Experience Store | Evidence Only `harvest`、`inspect`/`summarize`、确定性统计与支持度。 |
| 2. Rules | 带哈希、diff、rationale、source manifest 的 editable-block Patch IR。 |
| 3. Replay / Gate | 临时副本回放、静态 Gate Viewer、候选自审计、core/validation/held-out。 |
| 4. Model | 显式本地 adapter、超时、受限 JSON 接口与 rejected-candidate 约束。 |
| 5. 跨项目本地经验 | `collect` 与 `--experience-store` 汇总脱敏包；不联网。 |
| 6. Sleep | 本地有界闭环、`SKILL_EVOLUTION` 事件历史、预算、目标变更检测、最终只 stage。 |
| 7. 真实宿主评估 | Scripted、Codex、Claude Code 的隔离 fixture；规范化命令/最终答复事件、确定性评分、配对重复 rollout 与统计门禁。 |

真实宿主 fixture 是 proof-handoff 的 smoke test，不代表已经覆盖任意任务分布。要得到可用于
adopt 的已观测 Gate，需提供彼此隔离的 core、validation 与 held-out 任务，配置足够的配对
rollout，并将 `INCONCLUSIVE` 视为未通过。

```bash
# Phase 1：只处理结构化 AET JSON。
aet learn harvest --evidence .aet/evidence --output .aet/learn/experiences.json
aet learn inspect --experiences .aet/learn/experiences.json --output .aet/learn/inspection.json
aet learn mine --experiences .aet/learn/experiences.json --output .aet/learn/patterns.json

# Phase 2–3：候选只能改带标记的 editable block。
aet learn propose --engine rules --patterns .aet/learn/patterns.json \
  --target skills/agent-engineering-toolkit/SKILL.md --output .aet/learn/candidates/CAND-001
aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/core --suite eval/validation --suite eval/held-out \
  --output .aet/learn/replays/CAND-001.json
aet learn gate --candidate .aet/learn/candidates/CAND-001 --core eval/core \
  --validation eval/validation --held-out eval/held-out \
  --output .aet/learn/gates/CAND-001.json
aet learn viewer --gate .aet/learn/gates/CAND-001.json --output .aet/learn/CAND-001.html
aet learn stage --candidate .aet/learn/candidates/CAND-001 \
  --gate .aet/learn/gates/CAND-001.json --output .aet/learn/staged
```

Gate 会拒绝 immutable 字节变化、editable block 外修改、哈希异常、validation 与
held-out 重叠、候选自审计失败、回归、token/命令面预算超限和 workflow overuse 上升。
输出是指标向量，不是单一“信任分”。

`aet learn adopt --yes` 故意与 stage 分离：它会复核目标哈希，并写入本地 Decision
Ledger。`reject` 会留下拒绝理由；两者都不 commit 或 push。

### 真实 Agent 回放（显式启用）

静态 runner 只验证 Skill 文本合同，绝不冒充真实 Agent 行为。显式指定
`--runner scripted|codex|claude-code` 后，AET 会为 baseline/candidate 的每次
rollout 创建独立 fixture 副本，记录命令、Trace、工作区快照和最终答复；Gate 由这些
结构化事实而非 LLM Judge 判分。

```bash
aet learn runner list
aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/real-agent/core --runner codex --rollouts 3 \
  --runner-config runner.json --output .aet/learn/replays/CAND-001
```

`runner.json` 由用户在本地创建，例如包含
`{"aet_argv":["/absolute/path/to/aet"],"inherit_home":true}`。原始宿主输出只保留在
私有 rollout 目录，不会进入 Evidence Only 经验库。小样本是 `INCONCLUSIVE`，认证/模型/
启动失败是 `INFRASTRUCTURE_ERROR`；两者都不能 stage。Codex/Claude 的工作区隔离保护生产
仓库，但当前不宣称其提供 OS 级禁网或命令白名单，因此报告为 `PARTIAL`。

### 跨项目本地经验与定时执行

```bash
# 只显式汇集本地、去标识的 Evidence Only 包。
aet learn collect --experiences .aet/learn/experiences.json --store ~/.aet/experience
aet learn harvest --experience-store ~/.aet/experience --output .aet/learn/merged.json

# scheduler 可以调用，但必须保留明确预算和 stage-only 终点。
aet learn sleep --evidence .aet/evidence --target skills/agent-engineering-toolkit/SKILL.md \
  --core eval/core --validation eval/validation --held-out eval/held-out \
  --max-candidates 1 --max-replays 2 --max-model-calls 1 --timeout-seconds 120 \
  --output .aet/learn/nightly
```

默认不会读取 transcript、shell output、环境变量、secret，也不会上传、自动 commit、
push 或 adopt。精确边界见 [evolution boundary](evolution-boundary.md)。

## Context、决策与历史

```bash
aet context discover . --output .aet/context/manifest.json
aet context record --manifest .aet/context/manifest.json --read AGENTS.md
aet context verify --manifest .aet/context/manifest.json

aet decision init --output .aet/decisions.json
aet decision add --ledger .aet/decisions.json --id DEC-0001 \
  --claim "Keep proof execution explicit." --evidence-state EVIDENCED \
  --source docs/evolution-boundary.md
aet decision verify --ledger .aet/decisions.json

aet evolve plan . --question "Why was this release made?" --output .aet/evolve/plan.json
aet evolve collect . --question "Why was this release made?" --output .aet/evolve/run
aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
```

`context record --read` 只是 Agent/宿主“已读”的 attestation，不能证明模型理解或使用了
内容；`decision verify` 只验证记录的来源字节是否仍匹配，不宣称决策永远正确。
`evolve` 默认离线，只有显式 `--remote github` 才处理远端导出。

## 安装可移植 Skill 与 Hermes 迁移

请复制完整目录，而不是只复制 `SKILL.md`：

```bash
# 请从本仓库的 source checkout 执行（wheel 只包含 CLI，不携带 Skill 资源）：
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
cp -R skills/agent-engineering-toolkit ~/.codex/skills/
aet audit ~/.codex --format json --output ~/.aet/evidence/codex-audit.json
```

若 Hermes 的旧 Skill 路径已经被吸收到新的 `software-delivery-workflow`，AET 仍会把
旧引用保留为 `FAIL`，但在发现真实的 `.absorbed_into` 迁移元数据时，会给出本机替代
路径。这样既不掩盖失效指令，也不会只留下难以行动的路径错误。

## 验证与边界

在源码 checkout 中运行：

```bash
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  python -m unittest discover -s tests -v
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  aet audit . --strict --format json --output .aet/evidence/self-audit.json
uv build
```

AET 能验证记录的字节、显式命令退出码和声明产物处理；它不能证明模型理解指令、决策
永远正确、未 Trace 的命令运行过，也不能从缺失远端数据推断结论。使用前请阅读
[规则目录](rule-catalog.md)与[安全、隐私和保留边界](security-and-retention.md)。

## 贡献

见 [CONTRIBUTING.md](../CONTRIBUTING.md)。涉及证据语义的变更必须有测试、清晰的契约
更新与人工审阅的 intent 边界。
