# Real-time DeFi Price Manipulation Alert System
## Research and Engineering Implementation Plan

**Project:** 实时 DeFi 价格操纵预警系统  
**Scope:** Ethereum 主网一期  
**Date:** May 2026  
**Version:** 1.0  

---

## Abstract

本计划将实时 DeFi 价格操纵预警系统拆成可执行的工程步骤。系统目标是在 Ethereum pending 交易阶段完成模拟、cash-flow graph 构建、GraphSAGE 风险评分，并在高风险交易出块前发出可复核告警。冷路径使用 RAG 整合协议文档、审计报告、攻击复盘和标签证据，但不阻塞实时告警链路。

一期按“热路径实时检测 + 冷路径证据解释 + 分级告警处置”建设。默认不执行自动链上处置，所有严重告警只生成建议交易和 runbook 步骤，最终动作由人工、多签或授权负责人批准。

本计划包含：

1. 系统必须解决的问题和边界；
2. 分层系统架构和公共接口；
3. 从第 0 步到灰度上线的逐步实施步骤；
4. 数据、模型、RAG、控制台和处置流程的交付要求；
5. 离线评估、实时压测、回放测试和降级测试方案；
6. 16 周实施时间线、验收门槛和明确排除项。

---

## 1. Problem Statement and Implementation Goal

### 1.1 What the System Must Do

系统必须完成五类任务：

- **Pending 交易监听：** 从本地执行节点和备用 provider 获取 pending 交易、newHeads 和关键协议 logs。
- **未上链模拟：** 对 pending 交易使用 `debug_traceCall` 或 `trace_call` 生成标准化 trace、calls、logs、token transfers 和 state diff。
- **Cash-flow graph 构建：** 将单笔交易转换为多类型节点和多类型边，并补充 5 分钟地址上下文、1 小时协议上下文。
- **实时风险评分：** 使用 GraphSAGE 作为在线主模型，对每笔交易输出 risk score、severity 和 reason codes。
- **证据化告警：** 输出带图证据、文档证据、标签证据和建议动作的 `AlertEvent`，并支持人工复核和审计回放。

### 1.2 Why This Requires a Specialized Pipeline

普通链上监控或事后分析不能满足本项目要求，原因如下：

- **时间约束严格：** Ethereum slot 约 12 秒，系统目标是 P95 < 3 秒、P99 < 8 秒完成检测，RAG 解释不能进入热路径。
- **pending 状态不稳定：** pending 交易可能替换、失败、重排或被 MEV bundle 改变，系统必须记录来源、seen time、trace status 和降级原因。
- **价格操纵通常是结构性行为：** 单个 Transfer 或单个函数调用不足以判断风险，需要 cash-flow graph、call depth、协议角色、oracle 读写、滑点、利润路径和上下文窗口共同判断。
- **证据必须可复核：** 告警不能只给一个分数，必须能让分析员快速看到图路径、文档依据、标签来源和处置建议。

### 1.3 What This Plan Adds

| Contribution | Description | Why It Matters |
|---|---|---|
| 热路径/冷路径拆分 | 评分链路只做监听、模拟、图构建、模型、告警；RAG 异步补证据 | 避免解释生成拖慢出块前预警 |
| 标准事件 schema | 定义 `PendingTxEvent`、`TraceBundle`、`GraphInferenceRequest`、`AlertEvent` | 支持服务解耦、回放、审计和模型版本管理 |
| Cash-flow graph 规范 | 定义地址、资产、协议、transfer、call、context 特征 | 让模型输入稳定，并提升告警解释能力 |
| GraphSAGE 在线主模型 | 低延迟主模型，Temporal/Transformer 延后做二级复核 | 控制一期复杂度和推理成本 |
| EvidenceRef 证据引用 | 统一 `[GRAPH]`、`[DOC]`、`[LABEL]` 三类证据 | 保证告警说明可追溯 |
| 人工批准处置 | 默认只生成建议交易和 runbook，不自动执行 | 降低误报和权限风险 |

---

## 2. System Architecture

系统分为五层：数据接入层、trace 模拟层、图构建层、检测评分层、解释与处置层。

```text
Pending Tx / newHeads / Protocol Logs
        |
        v
Layer 1: Data Ingestion
  mempool-listener + head-log-listener
        |
        v
Layer 2: Trace Simulation
  debug_traceCall / trace_call workers
        |
        v
Layer 3: Graph Construction
  transfer-parser + cash-flow graph builder
        |
        v
Layer 4: Online Detection
  GraphSAGE scorer + threshold router
        |
        v
Layer 5: Alert and Evidence
  alert-orchestrator + async RAG + analyst console
```

### 2.1 Layer 1: Data Ingestion

目标是稳定获取 pending 交易和协议上下文。

**Inputs**

- 本地 Geth/Erigon 执行节点：`txpool`、`eth_subscribe newHeads`、`eth_subscribe logs`
- 备用执行节点
- 第三方 RPC/provider：仅作备份和补充

**Outputs**

- `PendingTxEvent`
- 区块头事件
- 协议 logs 事件

**Implementation Requirements**

- 所有 pending 交易按 `chain_id:tx_hash:source` 去重。
- 每条事件记录 `seen_at`、`source`、`chain_id`、`raw_tx`。
- provider 不能作为唯一真相；本地节点是主来源。
- 监听失败时切换备用节点，并记录故障时间和缺口范围。

### 2.2 Layer 2: Trace Simulation

目标是在交易上链前得到可解析的执行痕迹。

**Inputs**

- `PendingTxEvent`

**Outputs**

- `TraceBundle`

**Implementation Requirements**

- Geth 路径：优先使用 `debug_traceCall`，block tag 使用 `pending`。
- Erigon 路径：使用 `trace_call`，请求 `trace` 和 `stateDiff`。
- trace worker 要设置超时，例如 1.5 秒 P95 预算。
- trace 失败不能中断链路，应输出 `trace_status=failed` 的轻特征包。

### 2.3 Layer 3: Graph Construction

目标是把 trace 转成模型可消费、分析员可解释的 cash-flow graph。

**Inputs**

- `TraceBundle`
- ERC-20/ERC-721/ERC-1155 Transfer logs
- 5 分钟地址上下文
- 1 小时协议上下文

**Outputs**

- `GraphInferenceRequest`

**Implementation Requirements**

- 主图以单笔交易为单位。
- 节点类型至少包含 Address、Asset、Protocol。
- 边类型至少包含 Transfer、Call、Context。
- 上下文读取超时时仍然推理 `tx-only` 图。
- 缺失特征必须显式记录到 `feature_missing_flags`。

### 2.4 Layer 4: Online Detection

目标是在热路径内输出风险分数和原因码。

**Inputs**

- `GraphInferenceRequest`

**Outputs**

- Risk score
- Severity
- Reason codes
- Model metadata

**Implementation Requirements**

- 一期在线主模型使用 GraphSAGE。
- 模型包必须固定 `model_version`、`feature_ver`、`label_snapshot`、`threshold_profile`。
- 模型服务只接受匹配的 `feature_ver`；不匹配时退回规则基线。
- Temporal GNN 或 Graph Transformer 只作为 top 1-5% 高风险交易的二级复核，不进入一期主链路。

### 2.5 Layer 5: Alert and Evidence

目标是输出可复核告警，并在冷路径补齐解释。

**Inputs**

- Risk score
- Reason codes
- Graph evidence
- RAG document evidence
- Label evidence

**Outputs**

- `AlertEvent`
- RAG explanation
- Analyst review state

**Implementation Requirements**

- `score < 0.50`：仅记录。
- `0.50-0.75`：观察级，进入分析台队列。
- `0.75-0.90`：高危，触发 RAG 和人工复核。
- `>0.90`：严重，生成建议交易和升级通知，但默认不自动执行。
- RAG 只负责证据归并和自然语言说明，不修改风险分数。

---

## 3. Public Interfaces and Schemas

### 3.1 PendingTxEvent

```json
{
  "schema_ver": "pending-tx.v1",
  "event_id": "string",
  "hash": "0x...",
  "raw_tx": "0x...",
  "seen_at": "2026-05-12T00:00:00.000Z",
  "source": "local-geth-1",
  "chain_id": 1
}
```

### 3.2 TraceBundle

```json
{
  "schema_ver": "trace-bundle.v1",
  "event_id": "string",
  "tx_hash": "0x...",
  "calls": [],
  "logs": [],
  "token_transfers": [],
  "state_diff": {},
  "trace_source": "debug_traceCall",
  "trace_status": "ok",
  "trace_error": null
}
```

### 3.3 GraphInferenceRequest

```json
{
  "schema_ver": "graph-inference.v1",
  "event_id": "string",
  "graph_id": "1:0x...",
  "tx_hash": "0x...",
  "nodes": [],
  "edges": [],
  "feature_ver": "defi-pma-v1",
  "context_windows": ["tx-only", "5m-address", "1h-protocol"],
  "feature_missing_flags": []
}
```

### 3.4 AlertEvent

```json
{
  "schema_ver": "alert-event.v1",
  "event_id": "string",
  "tx_hash": "0x...",
  "score": 0.91,
  "severity": "critical",
  "reasons": ["abnormal_profit_path", "oracle_read_write_same_tx"],
  "evidence_refs": [
    "[GRAPH:0x...:attacker->pool->token]",
    "[DOC:uniswap-v3-oracle#twap-risk]",
    "[LABEL:vendor-a:0.82]"
  ],
  "suggested_actions": ["manual_review", "prepare_pause_tx"],
  "created_at": "2026-05-12T00:00:01.500Z"
}
```

### 3.5 EvidenceRef

只允许三类引用：

- `[GRAPH:tx_hash:edge_path]`
- `[DOC:source_id#section]`
- `[LABEL:provider:confidence]`

`LABEL` 只能作为风险参考，不能写成确定性身份结论或法律事实。

---

## 4. Step-by-Step Implementation Plan

### Step 0: Freeze Scope and Governance

**Goal:** 明确一期边界，避免项目同时承担多链、多协议和自动处置风险。

**Tasks**

1. 确认一期只做 Ethereum 主网。
2. 冻结目标协议白名单，例如 AMM、借贷、oracle 相关协议。
3. 定义价格操纵风险类型：oracle manipulation、flash-loan price pump、thin-liquidity swap、sandwich-assisted manipulation、cross-protocol liquidation cascade。
4. 明确默认不自动执行链上处置。
5. 建立数据授权清单：RPC、地址标签、实体归因、安全报告、审计报告。

**Deliverables**

- `scope.md`
- 目标协议白名单
- 风险类型字典
- 数据授权清单
- 初版值班与审批流程

**Gate Criterion**

- 链范围、协议范围、风险类型、处置权限均已签字确认。

### Step 1: Build Node and Provider Access

**Goal:** 搭好数据接入的主备基础设施。

**Tasks**

1. 部署一主一备执行节点，优先 Geth 或 Erigon。
2. 开启 HTTP、WebSocket、txpool、debug 或 trace API。
3. 配置第三方 provider 作为备用 pending stream 和 trace/debug 补充。
4. 建立节点健康检查：head lag、peer count、RPC latency、trace availability。
5. 记录节点切换策略和故障告警。

**Deliverables**

- 节点拓扑图
- RPC endpoint 配置
- health check 脚本
- provider fallback 规则

**Gate Criterion**

- 主备节点均可读取 pending 交易、newHeads、关键协议 logs，并能完成至少 100 笔 pending 交易模拟抽样。

### Step 2: Implement Message Bus and Event Schemas

**Goal:** 建立可回放、可审计的事件流。

**Tasks**

1. 创建 schema 仓库或 schema 目录。
2. 定义并校验 `PendingTxEvent`、`TraceBundle`、`GraphInferenceRequest`、`AlertEvent`。
3. 创建消息主题：`pending-tx.v1`、`trace-bundle.v1`、`graph-inference.v1`、`risk-score.v1`、`alert-event.v1`、`rag-explanation.v1`。
4. 为所有事件加入 `event_id`、`schema_ver`、`chain_id`、`created_at` 和幂等键。
5. 将原始 trace、图快照、模型输入、模型输出和告警版本落盘。

**Deliverables**

- JSON schema 或 Pydantic schema
- topic 命名规范
- replay storage 目录设计
- 幂等处理规则

**Gate Criterion**

- 同一 `PendingTxEvent` 重放两次不会产生重复告警。

### Step 3: Implement Mempool and Protocol Log Listener

**Goal:** 生成稳定的 `PendingTxEvent` 和协议上下文。

**Tasks**

1. 监听 pending tx。
2. 监听 `newHeads`。
3. 监听目标协议核心合约 logs。
4. 对 pending tx 做 hash 去重和 source 记录。
5. 对 replaced 或 dropped 交易保留状态更新。

**Deliverables**

- `mempool-listener`
- `head-log-listener`
- pending 交易样本集
- listener 延迟统计

**Gate Criterion**

- 连续运行 24 小时，无异常退出；pending event P95 入队延迟 ≤100ms。

### Step 4: Implement Pending Trace Simulation

**Goal:** 对 pending 交易生成标准化 `TraceBundle`。

**Tasks**

1. 实现 Geth `debug_traceCall` 路径。
2. 实现 Erigon `trace_call` 路径。
3. 统一 calls、logs、state diff、error 信息。
4. 实现 trace timeout、retry、provider fallback。
5. 对 trace 失败的交易生成轻特征包。

**Deliverables**

- `trace-worker`
- `TraceBundle` 标准化 mapper
- trace 成功率报表
- trace 失败样本分类

**Gate Criterion**

- 在抽样 pending 交易上 trace P95 ≤1.5s；trace 失败不阻断后续告警链路。

### Step 5: Parse Transfers and Protocol Semantics

**Goal:** 从 trace 和 logs 中提取资产流、调用路径和协议角色。

**Tasks**

1. 解析 ERC-20 Transfer。
2. 解析 ERC-721 和 ERC-1155 Transfer。
3. 提取 call depth、call type、selector、success、revert reason。
4. 建立协议合约角色表：pool、router、oracle、lending market、liquidation module。
5. 标准化 token decimals、amount_raw、amount_norm。

**Deliverables**

- transfer parser
- selector 字典
- 协议角色表
- token metadata 缓存

**Gate Criterion**

- 对历史已知复杂交易，Transfer 解析结果与区块浏览器或内部 replay 结果一致。

### Step 6: Build Cash-flow Graph

**Goal:** 构建 GraphSAGE 可消费的交易图。

**Tasks**

1. 定义 Address、Asset、Protocol 三类节点。
2. 定义 Transfer、Call、Context 三类边。
3. 构建 `tx-only` 主图。
4. 增补 `5m-address` 上下文。
5. 增补 `1h-protocol` 上下文。
6. 输出 `GraphInferenceRequest`。
7. 记录缺失特征和上下文超时情况。

**Deliverables**

- `graph-builder`
- 图特征字典
- 图快照样本
- graph serialization 格式

**Gate Criterion**

- graph build P95 ≤300ms；上下文超时时仍可输出 `tx-only` 图。

### Step 7: Build Rule Baseline

**Goal:** 在 GNN 前建立可解释基线和降级路径。

**Tasks**

1. 定义异常利润路径规则。
2. 定义 oracle read/write 同交易规则。
3. 定义超大滑点和薄流动性交易规则。
4. 定义 flash-loan in/out path 规则。
5. 输出 rule score 和 reason codes。

**Deliverables**

- rule baseline service
- reason code 字典
- 规则命中样本

**Gate Criterion**

- 模型不可用或 feature version 不匹配时，系统仍能输出低置信告警。

### Step 8: Train Offline GraphSAGE Model

**Goal:** 训练一期在线主模型。

**Tasks**

1. 收集正样本：exploit postmortem、安全报告、公开 incident 数据库。
2. 构建负样本：按协议、时期、交易复杂度分层抽样。
3. 将可疑未证实样本放入无标签池。
4. 固定训练集、验证集、回放集。
5. 训练 GraphSAGE：两层、hidden dim=64、dropout=0.1、mean aggregation、AdamW、lr=1e-3、class-balanced focal loss。
6. 输出 ROC-AUC、PR-AUC、Recall@FPR、lead time、校准误差。

**Deliverables**

- 训练数据快照
- GraphSAGE model artifact
- 离线评估报告
- threshold profile 初版

**Gate Criterion**

- AUC ≥0.95；Recall@FPR≤3% ≥0.80，或明确记录未达标原因和下一轮数据改进计划。

### Step 9: Serve Online Model

**Goal:** 将模型接入热路径。

**Tasks**

1. 封装模型服务 API。
2. 校验 `feature_ver`。
3. 输出 score、severity、reason codes、model metadata。
4. 实现 P95 ≤50ms 的推理目标。
5. 加入模型版本、阈值版本和特征缺失监控。

**Deliverables**

- `gnn-scorer`
- model registry
- inference latency dashboard
- model reject reason 日志

**Gate Criterion**

- 在 replay 集上，同一模型版本和同一输入输出稳定。

### Step 10: Implement Alert Orchestrator

**Goal:** 把分数转成分级告警和复核任务。

**Tasks**

1. 实现分级阈值：low、watch、high、critical。
2. 生成 `AlertEvent`。
3. 将 graph evidence、trace evidence、label evidence 关联到告警。
4. 对 high 和 critical 触发 RAG 异步任务。
5. 对 critical 生成建议交易和 runbook 步骤。

**Deliverables**

- `alert-orchestrator`
- severity router
- suggested action generator
- audit log

**Gate Criterion**

- `pending-tx.v1 -> alert-event.v1` 全链路可 replay；重复输入不重复告警。

### Step 11: Build RAG Knowledge Base

**Goal:** 为告警解释提供文档证据。

**Tasks**

1. 收集协议文档。
2. 收集审计报告。
3. 收集 exploit postmortem。
4. 收集安全厂商报告和治理提案。
5. 设计 document schema：`doc_id`、`source_type`、`protocol`、`section`、`date`、`severity`、`text`。
6. 建立 dense+sparse hybrid retrieval。
7. 使用 RRF 或 cross-encoder rerank。

**Deliverables**

- RAG document corpus
- indexer
- retrieval API
- document evidence template

**Gate Criterion**

- 对 high/critical 告警，RAG 能返回至少一个可追溯 `[DOC:source_id#section]`，无相关文档时必须显式说明 null retrieval。

### Step 12: Implement Evidence-Constrained Explanation

**Goal:** 让 LLM 只做证据归并，不修改风险分数。

**Tasks**

1. 设计解释模板：graph summary、doc summary、analyst note。
2. 要求每个事实性句子绑定 `evidence_refs`。
3. 禁止 LLM 改写 score、severity、reason codes。
4. RAG 超时后先发告警，再补 `rag-explanation.v1`。
5. 对无证据句子进行过滤。

**Deliverables**

- RAG explainer prompt
- evidence validator
- explanation API
- explanation audit log

**Gate Criterion**

- 高危告警解释可用率 100%；缺少证据引用的句子不会进入最终说明。

### Step 13: Build Analyst Console

**Goal:** 支持人工复核和处置闭环。

**Tasks**

1. 展示交易基础信息。
2. 展示 pending 模拟结果。
3. 展示 cash-flow graph 和关键路径。
4. 展示 reason codes 和模型元数据。
5. 展示 RAG 文档证据。
6. 展示标签来源和置信度。
7. 实现复核状态机：`new -> triaged -> escalated -> action_prepared -> approved/rejected -> resolved`。
8. 记录操作者、时间、理由和关联证据。

**Deliverables**

- analyst console
- alert detail page
- review state API
- audit trail export

**Gate Criterion**

- 分析员可以在一个页面完成从告警查看到处置决定的闭环。

### Step 14: Replay and Offline Evaluation

**Goal:** 用历史数据验证模型、阈值和解释质量。

**Tasks**

1. 构建历史 exploit replay 集。
2. 构建同期正常复杂交易集。
3. 回放 `pending-tx.v1 -> alert-event.v1`。
4. 统计误报、漏报、lead time 和阈值稳定性。
5. 比较规则基线、MLP、GCN/GAT/GIN、GraphSAGE。

**Deliverables**

- replay runner
- replay dataset
- offline evaluation report
- threshold calibration report

**Gate Criterion**

- 已知攻击进入 high/critical；误报样本可解释、可标注。

### Step 15: Real-time Load and Failure Testing

**Goal:** 验证线上延迟和降级能力。

**Tasks**

1. 压测 pending listener。
2. 压测 trace worker。
3. 压测 graph builder。
4. 压测 model inference。
5. 模拟主节点故障。
6. 模拟 provider 不可用。
7. 模拟 trace timeout。
8. 模拟 RAG timeout。
9. 模拟模型版本不匹配。

**Deliverables**

- load test report
- failure drill report
- SLO/SLA dashboard
- incident runbook

**Gate Criterion**

- 热路径 P95 <3s，P99 <8s；RAG 超时不阻塞告警；所有降级原因可审计。

### Step 16: Gray Launch and Operational Handoff

**Goal:** 小范围上线并交付运营。

**Tasks**

1. 选择 1-3 个协议灰度。
2. 只开启 watch/high/critical 告警，不自动处置。
3. 每日复盘误报、漏报、trace failure、RAG null retrieval。
4. 每周更新 threshold profile 和 runbook。
5. 完成值班交接和升级路径。

**Deliverables**

- gray launch report
- weekly review template
- production runbook
- go/no-go review packet

**Gate Criterion**

- 连续两周稳定运行，严重告警有完整图证据、审计日志和人工复核记录。

---

## 5. Graph Feature Dictionary

| Object | Required Fields | Optional Fields in Phase 1 |
|---|---|---|
| Address node | `address`、`account_type`、`is_contract`、`label_refs`、`in_degree_tx`、`out_degree_tx` | 5 分钟交互频率、1 小时资产多样性、历史风险分 |
| Asset node | `token_address`、`symbol`、`decimals`、`asset_type` | 流动性分层、是否稳定币、是否池子 LP token |
| Protocol node | `protocol_id`、`contract_role`、`pool_type` | 审计状态、治理权限、pause 能力 |
| Transfer edge | `from`、`to`、`asset`、`amount_raw`、`amount_norm`、`direction` | USD 估值、池内储备变化、利润归因 |
| Call edge | `caller`、`callee`、`selector`、`call_type`、`call_depth`、`success` | 是否 delegatecall、是否 oracle read/write、revert reason |
| Context edge | `window`、`relation_type`、`count`、`last_seen_at` | MEV bundle 位置、相邻 pending 交易冲突 |

---

## 6. Evaluation Framework

### 6.1 Tier 1: Offline Model Quality

| Metric | Purpose | Target |
|---|---|---|
| ROC-AUC | 总体分类能力 | ≥0.95 |
| PR-AUC | 不平衡样本下的高风险识别 | 项目内基线提升 |
| Recall@FPR≤3% | 低误报条件下的召回 | ≥0.80 |
| Lead time | 告警相对出块时间提前量 | 越高越好 |
| Calibration error | 分数是否可解释为风险概率 | 持续监控 |

### 6.2 Tier 2: Real-time Pipeline Quality

| Metric | Target |
|---|---|
| Pending event enqueue P95 | ≤100ms |
| Trace P95 | ≤1.5s |
| Graph build P95 | ≤300ms |
| Model inference P95 | ≤50ms |
| End-to-end detection P95 | <3s |
| End-to-end detection P99 | <8s |

### 6.3 Tier 3: Evidence and Analyst Utility

| Metric | Target |
|---|---|
| High/Critical graph evidence coverage | 100% |
| High/Critical explanation availability | 100%, 可异步补齐 |
| EvidenceRef validity | 100% |
| Duplicate alert rate | 接近 0 |
| Analyst review completion | 全部状态留痕 |

### 6.4 Statistical and Operational Protocol

- 固定回放集，不能参与调参。
- 每次模型发布记录 `model_version`、`feature_ver`、`label_snapshot`、`threshold_profile`。
- 每次阈值调整必须保留旧阈值、调整原因和回放结果。
- 所有误报、漏报必须进入复盘队列。

---

## 7. Implementation Stack and Configuration

| Component | Recommended Choice | Notes |
|---|---|---|
| Execution Node | Geth + Erigon optional | Geth 支持 `debug_traceCall`，Erigon 支持 `trace_call` |
| Message Bus | Kafka / Redpanda / NATS JetStream | 需要 replay 和幂等消费 |
| Storage | Postgres + object storage | 告警元数据入库，trace 和图快照入对象存储 |
| Graph Processing | Python + PyTorch Geometric / DGL | 以团队熟悉度为准 |
| Model | GraphSAGE | 一期在线主模型 |
| RAG Retrieval | Dense + sparse hybrid | Milvus、Qdrant 或本地向量库均可 |
| Embedding | BGE-M3 类多语模型 | 支持中英文文档 |
| Reranker | Cross-encoder reranker | 仅冷路径使用 |
| Dashboard | React / Next.js 或内部控制台框架 | 非热路径 |
| Observability | Prometheus + Grafana + structured logs | 监控延迟、失败率和降级原因 |

**Reproducibility requirements**

- 模型训练随机种子固定。
- 所有模型 artifact 和训练数据快照可追溯。
- 所有中间输出可落盘：trace、transfers、graph、score、alert、RAG explanation。
- 线上模型服务必须记录输入 `feature_ver` 和输出 `model_version`。

---

## 8. Alert Output Specification

### 8.1 Watch Alert

```markdown
## Watch Alert: [tx_hash]

Risk score: 0.62
Severity: watch
Reasons:
- mild_abnormal_profit_path
- high_slippage_swap

Evidence:
- [GRAPH:tx_hash:path_id]

Action:
- Monitor only
```

### 8.2 High Alert

```markdown
## High Risk Alert: [tx_hash]

Risk score: 0.84
Severity: high
Reasons:
- abnormal_profit_path
- flash_loan_in_out_same_tx

Graph Evidence:
- [GRAPH:tx_hash:path_id]

Document Evidence:
- [DOC:source_id#section]

Suggested Actions:
- manual_review
- notify_protocol_owner
```

### 8.3 Critical Alert

```markdown
## Critical Alert: [tx_hash]

Risk score: 0.93
Severity: critical
Reasons:
- oracle_read_write_same_tx
- abnormal_profit_path
- thin_liquidity_price_move

Evidence:
- [GRAPH:tx_hash:path_id]
- [DOC:source_id#section]
- [LABEL:provider:0.82]

Suggested Actions:
- open_incident_room
- prepare_pause_tx
- freeze_oracle_update

Execution Policy:
- Do not execute automatically.
- Requires multisig or authorized incident lead approval.
```

---

## 9. Implementation Timeline

| Phase | Duration | Key Deliverables | Gate Criterion |
|---|---:|---|---|
| Phase 0: Scope Freeze | Weeks 1-2 | 链范围、协议白名单、风险类型、数据授权清单 | 范围和权限签字确认 |
| Phase 1: Data Ingestion | Weeks 3-4 | 主备节点、pending listener、newHeads/log listener | 24 小时稳定运行，pending 入队 P95 ≤100ms |
| Phase 2: Trace and Parsing | Weeks 5-6 | trace worker、Transfer parser、协议角色表 | trace P95 ≤1.5s，失败可降级 |
| Phase 3: Graph and Baseline | Weeks 7-8 | cash-flow graph、规则基线、reason codes | graph build P95 ≤300ms |
| Phase 4: Model Training | Weeks 9-10 | GraphSAGE artifact、离线评估、阈值初版 | AUC 和 Recall@FPR 达到目标或完成复盘 |
| Phase 5: Alert and RAG | Weeks 11-12 | alert orchestrator、RAG KB、解释模板 | high/critical 告警有证据引用 |
| Phase 6: Console and Replay | Weeks 13-14 | 分析台、replay runner、审计日志 | 全链路可 replay，状态留痕完整 |
| Phase 7: Gray Launch | Weeks 15-16 | 双节点灰度、SLA 看板、runbook、演练报告 | 连续两周稳定运行 |

---

## 10. Go/No-Go Checklist

上线前必须满足：

1. `pending-tx.v1 -> alert-event.v1` 全链路可 replay。
2. 同一输入在同一模型版本下输出稳定。
3. high/critical 告警具备图证据、reason codes、审计日志和人工复核入口。
4. RAG 超时不阻塞告警，并记录超时原因。
5. 主执行节点、备用执行节点、第三方 provider 的切换演练完成。
6. 目标协议白名单、模型阈值、风险类型和标签授权清单已冻结。
7. 所有处置动作默认停留在建议交易或 runbook，不具备自动链上执行权限。

---

## 11. Scope Exclusions

| Excluded Feature | Reason for Exclusion |
|---|---|
| 多链同时上线 | 会显著增加节点、协议、标签和特征工程复杂度 |
| 自动链上处置 | 误报成本、合约权限和治理流程需要独立设计 |
| Graph Transformer 作为主模型 | 一期推理成本和复杂度过高，只做二级复核候选 |
| 全量实体归因系统 | 商业授权和法律边界复杂，一期只作为风险参考 |
| RAG 同步阻塞告警 | 会破坏热路径延迟目标 |
| 前端大屏优先 | 控制台服务于复核闭环，不应先于检测链路 |

---

## 12. Immediate Next Actions

1. 冻结 Ethereum 主网和首批目标协议白名单。
2. 搭建一主一备执行节点。
3. 实现 `debug_traceCall/trace_call` pending 模拟 PoC。
4. 创建四份 schema：`PendingTxEvent`、`TraceBundle`、`GraphInferenceRequest`、`AlertEvent`。
5. 用历史 exploit 和正常复杂交易构建 replay 集。
6. 先实现规则基线，再训练 GraphSAGE。
7. 建立协议文档、审计报告和 exploit postmortem 的 RAG 知识库。
8. 定义 high/critical 告警模板和人工复核状态机。
9. 完成降级演练和 go/no-go 评审后再灰度上线。
