# 真实案例：测试通过了，但证据已经过期

编码 Agent 报告测试通过。随后工作区继续变化，旧的绿色日志仍然存在。
原命令确实成功了，但它已经不能证明当前代码。

运行本地 Quick 演示：

```bash
./examples/stale-proof-demo.sh
```

关键状态变化如下：

```text
1/3 Record a bounded Quick proof for the exact workspace
2/3 Verify that the proof is fresh
freshness: EXACT_MATCH
3/3 Change the workspace without rerunning the proof
freshness: RELEVANT_FILES_CHANGED
```

`aet quick fresh` 不会改写历史执行结果。原命令仍然以退出码 `0` 成功，
但相关测试文件已经变化，因此旧证明不再适用于当前代码。

演示只使用临时 Git 仓库，不调用模型或网络服务。紧凑证明与新鲜度结果
保存在 `${TMPDIR:-/tmp}/aet-stale-proof-demo/.aet/proofs/`。

## 手动复现

```bash
aet quick proof \
  --relevant-path tests/test_add.py \
  --artifact reports/unit-tests.txt \
  --output .aet/proofs/unit-tests.json \
  -- python3 bin/run_proof.py

aet quick fresh --proof .aet/proofs/unit-tests.json
```

相关文件、声明产物、环境绑定或工作区基线变化后，再次运行
`aet quick fresh`。该命令只检查证明是否仍适用，不会重新执行测试。
