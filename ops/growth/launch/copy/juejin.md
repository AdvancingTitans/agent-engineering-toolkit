# 掘金教程提纲

Owner: `HUMAN_MAINTAINER`

Status: `COMPLETE`

公开证据：
`https://juejin.cn/spost/7667837994720280616`

Stop Rule: 如果 public wheel 不能从全新环境运行，或教程命令与 release 不
一致，停止发布。

## 标题

绿色测试日志为什么可能已经失效：用 AET 绑定命令与当前代码

## 教程路径

1. 安装 exact release；
2. 运行 `aet demo stale-proof --format json`；
3. 展开 fixture 的 `calc.py` 与 `unittest`；
4. 解释 `quick_proof` 如何记录 workspace、relevant files 与环境；
5. 展示 mutation 前后的 `quick_fresh`；
6. 在读者自己的仓库中声明两个真实 relevant paths；
7. 覆盖 Git 缺失、timeout、corrupt proof 与 `UNKNOWN`；
8. 给出 CI 集成边界：默认 Action 不执行任意 proof。

不要复制 README；正文必须包含可执行步骤、实际输出和失败路径。
