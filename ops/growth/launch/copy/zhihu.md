# 知乎长文提纲

Owner: `HUMAN_MAINTAINER`

Status: `COMPLETE`

公开证据：
`https://zhuanlan.zhihu.com/p/2065952961482715666`

Stop Rule: 如果文章无法给出精确 release、真实命令、环境和限制，就不发布；
如果只有泛流量而没有 demo 使用或技术讨论，暂停同主题投放。

## 标题方向

AI 编程 Agent 说“测试通过”时，它测的是现在这份代码吗？

## 结构

1. 先区分“命令当时真实通过”和“结果现在仍适用”。
2. 给出 `uvx ... aet demo stale-proof` 与完整三状态输出。
3. 解释 Quick Proof 绑定 argv、Git、relevant paths、环境与产物。
4. 解释为什么修改相关文件后保留历史 `PASS`，但 freshness 变成
   `RELEVANT_FILES_CHANGED`。
5. 对比 CI：CI 执行检查，AET 携带适用范围与 freshness。
6. 说明 AET 不是 Agent、不替代测试、不产生 holistic trust score。
7. 明确样本量：一个 fixture、一次可复现流程，不推导一般模型质量。
8. 链接原始 JSON、Schema、Release 和已知限制。

截图位：Hero PNG、JSON 输出、一个真实仓库 Evidence 工件。
