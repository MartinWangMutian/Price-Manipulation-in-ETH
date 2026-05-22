# 区块链金融风险监控原型

本仓库实现一个面向 Ethereum pending/replay 交易的 DeFi 价格操纵风险监控原型。系统目标是在交易确认前后尽早构建 cash-flow graph，结合规则基线和 GraphSAGE 风险模型输出可复核告警，并通过 RAG 证据解释辅助分析员复核。

当前仓库是可审计的工程原型：Provider-only replay、图构建、规则评分、告警、RAG 解释、报告审计和故障降级链路已经打通；GraphSAGE 训练入口、推理入口和模型版本协议已实现，但真实训练仍依赖完整 trace/API 数据、已晋升图级标签，以及 `torch`/`torch_geometric` 环境。

## 目录结构

```text
scripts/   独立 CLI 脚本和配套 *_selftest.py
config/    规则、协议白名单、selector 字典、模型 manifest 示例
schemas/   事件与 replay JSON Schema
data/      replay 数据、训练候选、上下文窗口、RAG 索引和控制台数据
ops/       命令索引、runbook、审计报告和生成报告
plan/      项目计划、执行清单、风险类型和研究材料
docs/      存储、图序列化等工程文档
ppt/       演示材料和网页 PPT 产物
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

已完成：

- Provider-only replay 链路和 110 条唯一评分链路验证。
- Cash-Flow Graph 构建器，包括 Protocol 节点、Call 边、Context 边结构。
- Context 窗口聚合器和图级标签导出器。
- 规则基线评分器、告警编排、RAG 解释和控制台数据构建。
- GraphSAGE 模型定义、训练脚本、推理入口、模型 manifest 协议和降级路径。
- 全量 `*_selftest.py` 自测通过。

仍需外部条件：

- 完整 trace-capable API 或本地 Geth/Erigon 节点，用于真实 call tree/state diff。
- 经分析员晋升的正负图级标签，导出为 `data/training/graph_labels.v1.json`。
- 安装 PyTorch / PyTorch Geometric 后训练并发布 `models/graphsage/latest/model.pt`。
- 真实离线评估：ROC-AUC、PR-AUC、Recall@FPR、校准曲线、消融实验和在线延迟测量。

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

运行规则基线：

```bash
python3 scripts/rule_baseline_scorer.py \
  --input data/replay/graph-inference.v1 \
  --write-replay \
  --write-hit-samples \
  --out ops/reports/rule-baseline-scorer.latest.json
```

导出图级训练标签：

```bash
python3 scripts/graph_label_exporter.py \
  --decisions data/training/label_promotion_decisions.seed.json \
  --graphs data/replay/graph-inference.v1 \
  --out data/training/graph_labels.v1.json \
  --report ops/reports/graph-label-exporter.latest.json
```

GraphSAGE 训练预检：

```bash
python3 scripts/graphsage_train.py \
  --graphs data/replay/graph-inference.v1 \
  --labels data/training/graph_labels.v1.json \
  --out-dir models/graphsage/latest \
  --report ops/reports/graphsage-train.latest.json \
  --dry-run
```

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

## 开发约定

- 新增或修改脚本时，优先添加相邻 `*_selftest.py`。
- JSON 输出保持 `indent=2`、`sort_keys=True`、UTF-8 和尾随换行。
- 生成报告默认写入 `ops/reports/`。
- `ppt/`、`outputs/`、`data/replay/` 是产物较多的区域，修改前确认任务是否需要触碰。

