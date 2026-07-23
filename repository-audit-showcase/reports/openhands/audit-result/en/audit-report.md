# AET Repository Audit — OpenHands

## Executive Summary

- Repository: `https://github.com/OpenHands/OpenHands`
- Commit: `96f902a9ac14bf5edfb2e47d759d75c91e4faf28`
- Audit scope: 5 include patterns, 5 exclusions
- Evidence collected: 107 files
- Runtime: 0.519s
- Maintainer review: `APPROVED`

This is a static engineering observation, not a defect or security-vulnerability report.

## Architecture View

![Agent flow](diagrams/agent-flow.svg)

## Evidence Map

![Evidence chain](diagrams/evidence-chain.svg)

## Findings

### AET-REPO-001 — Repository revision is reproducibly locked

- Status: `PASS`
- Severity: `INFO`
- Impact: `high` — A mismatched or dirty checkout makes line-level evidence non-reproducible.
- Evidence:
  - `.git` — HEAD=96f902a9ac14bf5edfb2e47d759d75c91e4faf28
- Recommendation: Checkout the locked commit and remove local repository changes.

### AET-REPO-002 — License and prohibited-path boundary is enforced

- Status: `PASS`
- Severity: `INFO`
- Impact: `high` — A license mismatch or prohibited path in the evidence set invalidates publication.
- Evidence:
  - `LICENSE:1` — git_blob=572bb259491e4e2adafee0c03db0d4ed419e6b9a; expected=572bb259491e4e2adafee0c03db0d4ed419e6b9a
- Recommendation: Restore the locked license file and keep prohibited paths outside every include pattern.

### AET-REPO-003 — Application orchestration evidence is visible

- Status: `PASS`
- Severity: `INFO`
- Impact: `high` — Static conversation, runtime, event, and verification evidence is present in the application-server scope.
- Evidence:
  - `openhands/app_server/app_conversation/README.md:1` — category=agent; sha256=a8db9c739e703bfb7a03d0d6c73249498580cf6721b64293bb3aa7032ab18ce1
  - `openhands/app_server/app_conversation/app_conversation_info_service.py:1` — category=agent; sha256=26fade1d9d62e1decaa42e7a60f436ee9d08b550ff59e58a1528229e32bed7a1
  - `openhands/app_server/app_conversation/README.md:1` — category=runtime; sha256=a8db9c739e703bfb7a03d0d6c73249498580cf6721b64293bb3aa7032ab18ce1
  - `openhands/app_server/app_conversation/app_conversation_info_service.py:1` — category=runtime; sha256=26fade1d9d62e1decaa42e7a60f436ee9d08b550ff59e58a1528229e32bed7a1
  - `openhands/app_server/event/README.md:1` — category=trajectory; sha256=4a0222a86861bf22fea46fd3f0d32109ce36481f42ac121a84b233439695be39
  - `openhands/app_server/event/aws_event_service.py:1` — category=trajectory; sha256=5ed340b11987c4004767bd0fd0ec2ed8497c41a2d19edff4a8fca4d29ab9c0fb
  - `tests/unit/app_server/file_store/test_file_store.py:1` — category=verification; sha256=6a89be0e5ed3a4c51909f2d8366e911e861eefb49ab3cc716aff9992567064b1
  - `tests/unit/app_server/test_agent_server_env_override.py:1` — category=verification; sha256=8ab4be7e7217b6cf2b6604c7a1f5e28c7c14ad675d4b36c90a4b1b44f2a2a364
- Recommendation: Keep cross-package Agent execution claims explicitly bound to versioned SDK and verification evidence.

### AET-REPO-004 — Runtime isolation and recovery evidence is inspectable

- Status: `PASS`
- Severity: `INFO`
- Impact: `high` — Static runtime, isolation, and failure-handling evidence is present in the bounded scope.
- Evidence:
  - `openhands/app_server/app_conversation/README.md:1` — category=runtime; sha256=a8db9c739e703bfb7a03d0d6c73249498580cf6721b64293bb3aa7032ab18ce1
  - `openhands/app_server/app_conversation/app_conversation_info_service.py:1` — category=runtime; sha256=26fade1d9d62e1decaa42e7a60f436ee9d08b550ff59e58a1528229e32bed7a1
  - `openhands/app_server/app_conversation/app_conversation_info_service.py:88` — category=isolation; sha256=26fade1d9d62e1decaa42e7a60f436ee9d08b550ff59e58a1528229e32bed7a1
  - `openhands/app_server/app_conversation/app_conversation_models.py:116` — category=isolation; sha256=7c8cf495789001a5925774f23a678b2d6da122942f9555fcf520abe3b2b7e69a
  - `openhands/app_server/app_conversation/app_conversation_models.py:170` — category=recovery; sha256=7c8cf495789001a5925774f23a678b2d6da122942f9555fcf520abe3b2b7e69a
  - `openhands/app_server/app_conversation/app_conversation_router.py:379` — category=recovery; sha256=864bff55884872eac7de6b2ce6f89a19df3d9db99e9ade993d096f308f051259
- Recommendation: Bind sandbox actions and recovery paths to explicit, inspectable result evidence.

### AET-REPO-005 — The external Agent core remains outside this checkout

- Status: `UNKNOWN`
- Severity: `WARN`
- Impact: `medium` — The checkout evidences an external Agent dependency but not a local Agent-core definition. Missing categories: local_agent_definition.
- Evidence:
  - `pyproject.toml:1` — category=external; sha256=81c65766ba4b3c41fc3cc1007c6274de1cbdf4ae2b298fd782ee790fc9172b0b
- Recommendation: Audit the separately versioned Agent SDK before making end-to-end execution claims.

## Publication Boundary

Static analysis of a public upstream repository. No source code is redistributed, and no affiliation or upstream endorsement is implied.
