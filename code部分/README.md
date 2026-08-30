# 区块链金融风险监控原型

本仓库实现一个面向 Ethereum pending/replay 交易的 DeFi 价格操纵风险监控原型。系统目标是在交易确认前后尽早构建 cash-flow graph，结合规则基线和 GraphSAGE 风险模型输出可复核告警，并通过 RAG 证据解释辅助分析员复核。

当前仓库是可审计的工程原型：Provider-only replay、真实历史 trace、富图构建、规则评分、告警、RAG 解释、报告审计和故障降级链路已经打通；GraphSAGE 训练入口、推理入口和模型版本协议已实现。Stage 4 已将 57 张候选图冻结为 55 张工程烟雾标签（5 正、50 负），并完成事件/相关地址分组的 60/20/20 无泄漏切分；两笔角色证据不足的事件相关交易保留为 `unlabeled`。Stage 5 已锁定独立 PyTorch/PyG 环境，并通过最小训练闭环；Stage 6 已将旧的全量单批脚本升级为严格消费冻结 split manifest 的可复现 mini-batch 训练器，支持 validation PR-AUC 早停、最佳/最后 checkpoint、恢复训练和完整运行产物。该快照仍不支持研究级结论，下一步是 Stage 7 的 57 笔工程烟雾训练与基线对比。

## 目录结构

```text
scripts/   独立 CLI 脚本和配套 *_selftest.py
config/    规则、协议白名单、selector 字典、模型 manifest 示例
schemas/   事件与 replay JSON Schema
data/      replay 数据、训练候选、上下文窗口、RAG 索引和控制台数据
ops/       命令索引、runbook、审计报告和生成报告
docs/      存储、图序列化等工程文档
```

## 核心流水线

1. **Pending / trace 输入**：采集 pending 或历史交易，生成 `trace-bundle.v1`。
2. **Trace 解析**：从 calls/logs 中提取 call tree、ERC 转账和函数 selector。
3. **协议角色增强**：用 `config/protocol_roles.json` 标注 Uniswap、Aave、Compound、Chainlink 等协议角色。
4. **Context 窗口构建**：生成 `5m-address` 和 `1h-protocol` 上下文摘要。
5. **Cash-Flow Graph 构建**：生成 Address、Asset、Protocol、Transaction、Context 节点，以及 Transfer、Call、Context 边。
6. **风险评分**：当前规则基线可直接运行；GraphSAGE 在模型包可用时作为主模型，否则降级到规则基线。
7. **告警与解释**：生成 `alert-event.v1`，并用 RAG 证据模板生成解释。
8. **审计与评估**：运行 replay check、quality check、failure drill、offline evaluation 和 readiness audit。

## 当前状态


- Provider-only replay 链路和 110 条唯一评分链路验证。
- 57 笔 Ethereum Mainnet 历史交易的 `trace_transaction` 回放、原始 trace 哈希和谱系审计。
- 57 张富 Cash-Flow Graph，包含 11,521 条 Call 边、492 条 Transfer 边和 48 条 Context 边，严格质量门控错误数为 0。
- Cash-Flow Graph 构建器，包括 Protocol 节点、Call 边、Context 边结构。
- Context 窗口聚合器和图级标签导出器。
- 规则基线评分器、告警编排、RAG 解释和控制台数据构建。
- GraphSAGE 模型定义、训练脚本、推理入口、模型 manifest 协议和降级路径。
- 全量 `*_selftest.py` 自测通过。


## 快速开始

建议使用 Python 3.12。仓库没有根 package manifest，脚本按独立 CLI 运行。

```bash
python3 scripts/alert_orchestrator_selftest.py
```

运行全部自测：

```bash
for t in scripts/*_selftest.py; do python3 "$t"; done
```

校验 Schema：

```bash
python3 scripts/validate_schemas.py
```

## 常用命令

完整命令链见 [ops/command_index.md](ops/command_index.md)。常用阶段命令如下。

解析 trace：

```bash
python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/trace-parser.latest.json
```

协议角色增强：

```bash
python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.latest.json
```

构建 Context 窗口：

```bash
python3 scripts/context_window_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --address-out data/context/address-context.v1.json \
  --protocol-out data/context/protocol-context.v1.json \
  --report ops/reports/context-window-builder.latest.json
```

构建 Cash-Flow Graph：

```bash
python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --address-context data/context/address-context.v1.json \
  --protocol-context data/context/protocol-context.v1.json \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.latest.json
```

对真实历史 trace 生成的富图运行严格谱系与结构审计：

```bash
python3 scripts/rich_graph_quality_audit.py \
  --trace-input data/replay/trace-bundle.v1/dt=2026-08-29 \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-29 \
  --protocol-input data/replay/protocol-features.v1/dt=2026-08-29 \
  --graph-input data/replay/graph-inference.v1/dt=2026-08-29 \
  --out ops/reports/rich-graph-quality-audit.latest.json
```

运行规则基线：

```bash
python3 scripts/rule_baseline_scorer.py \
  --input data/replay/graph-inference.v1 \
  --write-replay \
  --write-hit-samples \
  --out ops/reports/rule-baseline-scorer.latest.json
```

Stage 4 标签证据复核、图级标签导出与无泄漏切分见
[`ops/label_promotion_runbook.md`](ops/label_promotion_runbook.md)。冻结图级标签可直接重新导出：

```bash
python3 scripts/graph_label_exporter.py \
  --decisions data/training/label_promotion_decisions.stage4.v1.json \
  --graphs data/replay/graph-inference.v1/dt=2026-08-29 \
  --out data/training/graph_labels.stage4.v1.json \
  --report ops/reports/graph-label-exporter.stage4.latest.json
```

GraphSAGE 独立环境与最小训练闭环见
[`ops/full_training_stage5_runbook.md`](ops/full_training_stage5_runbook.md)：

```bash
python3 -m venv .venv-graphsage
.venv-graphsage/bin/python -m pip install \
  -r requirements/graphsage-stage5.lock.txt
.venv-graphsage/bin/python scripts/training_environment_audit.py
.venv-graphsage/bin/python scripts/training_smoke_test.py
```

Stage 6 可复现训练器见
[`ops/full_training_stage6_runbook.md`](ops/full_training_stage6_runbook.md)：

```bash
.venv-graphsage/bin/python scripts/graphsage_train.py \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --device auto \
  --seed 20260830 \
  --batch-size 8 \
  --epochs 100 \
  --patience 15 \
  --monitor pr_auc \
  --run-id stage7-engineering-smoke
```

该入口只加载 `train` 和 `validation`；冻结的 `held_out_test` 在模型和阈值锁定前不得评估。

GraphSAGE 推理入口：

```bash
python3 scripts/graphsage_inference_service.py \
  --input data/replay/graph-inference.v1 \
  --model-dir models/graphsage/latest \
  --out ops/reports/graphsage-inference.latest.json
```

## 配置与安全

- 不要提交真实密钥。`.env.local` 和本地联系人配置应保留在本地。
- 对外共享报告前运行 secrets 扫描：

```bash
python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json
```

- 示例配置放在 `config/*.example.json` 或 `ops/*.env.example`。
