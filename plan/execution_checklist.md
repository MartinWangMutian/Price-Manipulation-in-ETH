# Real-time DeFi 价格操纵预警系统执行 Checklist
**分层任务清单 — 从范围冻结到灰度上线**

> 使用说明：完成一项打 `[x]`。每个 Phase 开始前先确认前一个 Phase 的 Gate Criterion 已通过。  
> 时间估算按 16 周一期建设节奏编排；实际进度可根据节点资源、数据授权和模型数据质量调整。

---

## Phase 0 — 范围冻结与治理准备（第1-2周）

### P0-A 项目范围冻结

**依赖：无**

- [ ] 确认一期只覆盖 Ethereum 主网
- [ ] 明确不在一期同时支持多链
- [ ] 确认目标 slot/延迟目标：
  - [ ] 热路径 P95 < 3 秒
  - [ ] 热路径 P99 < 8 秒
  - [ ] RAG 异步执行，不进入热路径预算
- [ ] 冻结首批目标协议白名单：
  - [ ] AMM / DEX
  - [ ] Lending market
  - [ ] Oracle 相关合约
  - [ ] Router / Aggregator 合约
- [ ] 为每个协议记录：
  - [ ] protocol_id
  - [ ] 合约地址
  - [ ] 合约角色
  - [ ] pause / guardian / emergency 权限
  - [ ] 文档与审计报告链接

### P0-B 风险类型与处置边界

- [ ] 定义一期价格操纵风险类型：
  - [ ] oracle_manipulation
  - [ ] flash_loan_price_pump
  - [ ] thin_liquidity_swap
  - [ ] sandwich_assisted_manipulation
  - [ ] cross_protocol_liquidation_cascade
- [ ] 定义 reason code 命名规范
- [ ] 明确默认不自动执行链上处置
- [ ] 明确 critical 告警只生成建议交易和 runbook
- [ ] 明确人工、多签或授权负责人审批流程
- [ ] 定义第三方标签的使用边界：只作为风险参考，不作为法律事实

### P0-C 数据授权与项目文档

- [ ] 建立数据授权清单：
  - [ ] 本地节点数据
  - [ ] 第三方 RPC/provider
  - [ ] 地址标签
  - [ ] 实体归因
  - [ ] 安全报告
  - [ ] 审计报告
  - [ ] 协议文档
- [ ] 创建 `scope.md`
- [ ] 创建风险类型字典
- [ ] 创建目标协议白名单
- [ ] 创建初版值班与审批流程

**Phase 0 Gate Criterion：** 链范围、协议范围、风险类型、数据授权和处置权限均已确认。

---

## Phase 1 — 节点、Provider 与事件基础设施（第3-4周）

### P1-A 执行节点与 Provider 接入

**依赖：Phase 0 完成**

- [ ] 部署主执行节点
- [ ] 部署备用执行节点
- [ ] 选择节点客户端：
  - [ ] Geth 路径验证 `debug_traceCall`
  - [ ] Erigon 路径验证 `trace_call`
- [ ] 开启 HTTP RPC
- [ ] 开启 WebSocket RPC
- [ ] 开启 `txpool` API
- [ ] 开启 `debug` 或 `trace` API
- [ ] 配置第三方 provider 作为备用 pending stream
- [ ] 配置第三方 provider 作为 trace/debug 补充来源
- [ ] 建立 RPC endpoint 配置文件

### P1-B 节点健康检查

- [ ] 实现 head lag 检查
- [ ] 实现 peer count 检查
- [ ] 实现 RPC latency 检查
- [ ] 实现 trace availability 检查
- [ ] 实现 WebSocket 订阅可用性检查
- [ ] 建立主备节点切换规则
- [ ] 记录故障时间、恢复时间和缺口范围
- [ ] 输出节点健康检查报表

### P1-C 消息主题与 Schema 基础

- [ ] 创建 schema 目录
- [ ] 定义 `PendingTxEvent`
- [ ] 定义 `TraceBundle`
- [ ] 定义 `GraphInferenceRequest`
- [ ] 定义 `AlertEvent`
- [ ] 为所有事件加入：
  - [ ] `event_id`
  - [ ] `schema_ver`
  - [ ] `chain_id`
  - [ ] `created_at`
  - [ ] 幂等键
- [ ] 创建消息主题：
  - [ ] `pending-tx.v1`
  - [ ] `trace-bundle.v1`
  - [ ] `graph-inference.v1`
  - [ ] `risk-score.v1`
  - [ ] `alert-event.v1`
  - [ ] `rag-explanation.v1`
- [ ] 设计 replay storage 目录
- [ ] 设计 trace、图快照、模型输入、模型输出和告警版本的落盘格式

**Phase 1 Gate Criterion：** 主备节点均可读取 pending 交易、newHeads、关键协议 logs，并能完成至少 100 笔 pending 交易模拟抽样；事件 schema 可校验。

---

## Phase 2 — Mempool 监听与 Pending Trace 模拟（第5-6周）

### P2-A Mempool 与协议日志监听

**依赖：Phase 1 完成**

- [ ] 实现 `mempool-listener`
- [ ] 监听 pending tx
- [ ] 监听 `newHeads`
- [ ] 监听目标协议核心合约 logs
- [ ] 对 pending tx 按 `chain_id:tx_hash:source` 去重
- [ ] 记录 `seen_at`
- [ ] 记录 `source`
- [ ] 记录 `raw_tx`
- [ ] 记录 replaced / dropped 交易状态
- [ ] 输出 pending 交易样本集
- [ ] 统计 listener 入队延迟

### P2-B Pending Trace Worker

- [ ] 实现 Geth `debug_traceCall` 路径
- [ ] 实现 Erigon `trace_call` 路径
- [ ] block tag 使用 `pending`
- [ ] 请求并标准化 calls
- [ ] 请求并标准化 logs
- [ ] 请求并标准化 state diff
- [ ] 统一 trace error 格式
- [ ] 设置 trace timeout
- [ ] 实现 retry 策略
- [ ] 实现 provider fallback
- [ ] 对 trace 失败交易生成 `trace_status=failed` 轻特征包
- [ ] 生成 trace 成功率报表
- [ ] 生成 trace 失败样本分类

### P2-C TraceBundle 校验

- [ ] 校验 `TraceBundle.schema_ver`
- [ ] 校验 `tx_hash`
- [ ] 校验 `trace_source`
- [ ] 校验 `trace_status`
- [ ] 校验 calls/logs/state_diff 字段类型
- [ ] 保存原始 trace
- [ ] 保存标准化 trace
- [ ] 对同一 pending tx 重放两次，确认不会产生重复下游事件

**Phase 2 Gate Criterion：** listener 连续运行 24 小时无异常退出；pending event P95 入队延迟 ≤100ms；trace P95 ≤1.5s；trace 失败不阻断后续链路。

---

## Phase 3 — Transfer 解析、协议语义与 Cash-flow Graph（第7-8周）

### P3-A Transfer 与 Call 解析

**依赖：Phase 2 完成**

- [ ] 实现 ERC-20 Transfer 解析
- [ ] 实现 ERC-721 Transfer 解析
- [ ] 实现 ERC-1155 Transfer 解析
- [ ] 标准化 token decimals
- [ ] 标准化 `amount_raw`
- [ ] 标准化 `amount_norm`
- [ ] 提取 call depth
- [ ] 提取 call type
- [ ] 提取 function selector
- [ ] 提取 call success
- [ ] 提取 revert reason
- [ ] 建立 selector 字典
- [ ] 建立 token metadata 缓存

### P3-B 协议角色表

- [ ] 建立协议合约角色表
- [ ] 标记 pool 合约
- [ ] 标记 router 合约
- [ ] 标记 oracle 合约
- [ ] 标记 lending market 合约
- [ ] 标记 liquidation module 合约
- [ ] 标记 pause / guardian / owner 权限相关合约
- [ ] 将协议角色写入图特征

### P3-C Cash-flow Graph Builder

- [ ] 定义 Address node
- [ ] 定义 Asset node
- [ ] 定义 Protocol node
- [ ] 定义 Transfer edge
- [ ] 定义 Call edge
- [ ] 定义 Context edge
- [ ] 构建 `tx-only` 主图
- [ ] 增补 `5m-address` 上下文
- [ ] 增补 `1h-protocol` 上下文
- [ ] 支持上下文读取超时后只输出 `tx-only` 图
- [ ] 记录 `feature_missing_flags`
- [ ] 输出 `GraphInferenceRequest`
- [ ] 保存图快照样本
- [ ] 定义 graph serialization 格式

### P3-D 图质量验证

- [ ] 选择历史已知复杂交易样本
- [ ] 对比 Transfer 解析结果与区块浏览器或内部 replay
- [ ] 人工检查 10 个 cash-flow graph
- [ ] 验证节点类型是否正确
- [ ] 验证边方向是否正确
- [ ] 验证 call depth 是否正确
- [ ] 验证协议角色是否正确
- [ ] 统计 graph build latency

**Phase 3 Gate Criterion：** 历史复杂交易解析结果一致；graph build P95 ≤300ms；上下文超时时仍可输出 `tx-only` 图。

---

## Phase 4 — 规则基线、训练数据与 GraphSAGE 模型（第9-10周）

### P4-A 规则基线

**依赖：Phase 3 完成**

- [ ] 定义异常利润路径规则
- [ ] 定义 oracle read/write 同交易规则
- [ ] 定义超大滑点规则
- [ ] 定义薄流动性交易规则
- [ ] 定义 flash-loan in/out path 规则
- [ ] 输出 rule score
- [ ] 输出 reason codes
- [ ] 建立 reason code 字典
- [ ] 保存规则命中样本
- [ ] 将规则基线接入模型不可用降级路径

### P4-B 训练数据构建

- [ ] 收集 exploit postmortem
- [ ] 收集安全报告
- [ ] 收集公开 incident 数据库
- [ ] 标注正样本：
  - [ ] 攻击类型
  - [ ] 受影响协议
  - [ ] 攻击收益
  - [ ] 关键交易
- [ ] 构建负样本：
  - [ ] 按协议分层抽样
  - [ ] 按时期分层抽样
  - [ ] 按交易复杂度分层抽样
- [ ] 将可疑未证实样本放入无标签池
- [ ] 固定训练集
- [ ] 固定验证集
- [ ] 固定回放集，确保不参与调参

### P4-C GraphSAGE 离线训练

- [ ] 训练 GraphSAGE 主模型
- [ ] 固定模型配置：
  - [ ] 2 layers
  - [ ] hidden dim = 64
  - [ ] dropout = 0.1
  - [ ] mean aggregation
  - [ ] AdamW
  - [ ] lr = 1e-3
  - [ ] class-balanced focal loss
- [ ] 记录 `model_version`
- [ ] 记录 `feature_ver`
- [ ] 记录 `label_snapshot`
- [ ] 记录 `threshold_profile`
- [ ] 输出 ROC-AUC
- [ ] 输出 PR-AUC
- [ ] 输出 Recall@FPR≤3%
- [ ] 输出 lead time
- [ ] 输出 calibration error
- [ ] 保存 GraphSAGE model artifact
- [ ] 生成离线评估报告

### P4-D 对照实验

- [ ] 跑规则基线
- [ ] 跑 MLP baseline
- [ ] 跑 GCN baseline
- [ ] 跑 GAT baseline
- [ ] 跑 GIN baseline
- [ ] 跑 GraphSAGE
- [ ] 对比 ROC-AUC / PR-AUC / Recall@FPR
- [ ] 输出 threshold profile 初版

**Phase 4 Gate Criterion：** GraphSAGE AUC ≥0.95 且 Recall@FPR≤3% ≥0.80；若未达标，必须记录原因和下一轮数据改进计划；规则基线可作为降级路径运行。

---

## Phase 5 — 在线模型服务、告警编排与 RAG 知识库（第11-12周）

### P5-A 在线模型服务

**依赖：Phase 4 完成**

- [ ] 封装 `gnn-scorer` API
- [ ] 校验输入 `feature_ver`
- [ ] 校验模型 `model_version`
- [ ] 输出 risk score
- [ ] 输出 severity
- [ ] 输出 reason codes
- [ ] 输出 model metadata
- [ ] 记录模型版本、阈值版本和特征缺失
- [ ] 建立 model registry
- [ ] 建立 inference latency dashboard
- [ ] 对 feature version 不匹配输出 `model_reject_reason`
- [ ] 接入规则基线 fallback

### P5-B Alert Orchestrator

- [ ] 实现 severity router
- [ ] 实现分级阈值：
  - [ ] `<0.50` low
  - [ ] `0.50-0.75` watch
  - [ ] `0.75-0.90` high
  - [ ] `>0.90` critical
- [ ] 生成 `AlertEvent`
- [ ] 关联 graph evidence
- [ ] 关联 trace evidence
- [ ] 关联 label evidence
- [ ] 对 high 告警触发 RAG 异步任务
- [ ] 对 critical 告警触发 RAG 异步任务
- [ ] 对 critical 生成建议交易
- [ ] 对 critical 生成 runbook 步骤
- [ ] 写入 audit log
- [ ] 验证 `pending-tx.v1 -> alert-event.v1` 全链路 replay

### P5-C RAG Knowledge Base

- [ ] 收集协议文档
- [ ] 收集审计报告
- [ ] 收集 exploit postmortem
- [ ] 收集安全厂商报告
- [ ] 收集治理提案
- [ ] 设计 document schema：
  - [ ] `doc_id`
  - [ ] `source_type`
  - [ ] `protocol`
  - [ ] `section`
  - [ ] `date`
  - [ ] `severity`
  - [ ] `text`
- [ ] 建立 dense retrieval
- [ ] 建立 sparse retrieval
- [ ] 实现 dense+sparse hybrid retrieval
- [ ] 实现 RRF 或 cross-encoder rerank
- [ ] 输出 document evidence template
- [ ] 支持 null retrieval 显式说明

### P5-D Evidence-Constrained Explanation

- [ ] 设计 graph summary 模板
- [ ] 设计 doc summary 模板
- [ ] 设计 analyst note 模板
- [ ] 要求每个事实性句子绑定 `evidence_refs`
- [ ] 禁止 LLM 改写 score
- [ ] 禁止 LLM 改写 severity
- [ ] 禁止 LLM 改写 reason codes
- [ ] RAG 超时后先发告警
- [ ] RAG 超时后补 `rag-explanation.v1`
- [ ] 过滤缺少证据引用的句子
- [ ] 建立 explanation audit log

**Phase 5 Gate Criterion：** 在线推理 P95 ≤50ms；high/critical 告警有 EvidenceRef；RAG 超时不阻塞告警；`pending-tx.v1 -> alert-event.v1` 可 replay。

---

## Phase 6 — 分析控制台、回放评估与故障演练（第13-14周）

### P6-A Analyst Console

**依赖：Phase 5 完成**

- [ ] 实现告警列表页
- [ ] 实现告警详情页
- [ ] 展示交易基础信息
- [ ] 展示 pending 模拟结果
- [ ] 展示 cash-flow graph
- [ ] 展示关键路径
- [ ] 展示 reason codes
- [ ] 展示模型元数据
- [ ] 展示 RAG 文档证据
- [ ] 展示标签来源和置信度
- [ ] 展示建议动作
- [ ] 实现复核状态机：
  - [ ] `new`
  - [ ] `triaged`
  - [ ] `escalated`
  - [ ] `action_prepared`
  - [ ] `approved`
  - [ ] `rejected`
  - [ ] `resolved`
- [ ] 记录操作者
- [ ] 记录状态变化时间
- [ ] 记录复核理由
- [ ] 记录关联证据
- [ ] 支持 audit trail export

### P6-B Replay and Offline Evaluation

- [ ] 构建历史 exploit replay 集
- [ ] 构建同期正常复杂交易集
- [ ] 回放 `pending-tx.v1 -> alert-event.v1`
- [ ] 统计误报
- [ ] 统计漏报
- [ ] 统计 lead time
- [ ] 统计阈值稳定性
- [ ] 评估 high/critical graph evidence coverage
- [ ] 评估 high/critical explanation availability
- [ ] 评估 EvidenceRef validity
- [ ] 生成 offline evaluation report
- [ ] 生成 threshold calibration report

### P6-C Real-time Load Test

- [ ] 压测 pending listener
- [ ] 压测 trace worker
- [ ] 压测 graph builder
- [ ] 压测 model inference
- [ ] 压测 alert orchestrator
- [ ] 统计 pending event enqueue P95
- [ ] 统计 trace P95
- [ ] 统计 graph build P95
- [ ] 统计 model inference P95
- [ ] 统计 end-to-end detection P95
- [ ] 统计 end-to-end detection P99
- [ ] 生成 load test report

### P6-D Failure Drill

- [ ] 模拟主节点故障
- [ ] 模拟备用节点故障
- [ ] 模拟第三方 provider 不可用
- [ ] 模拟 trace timeout
- [ ] 模拟 RAG timeout
- [ ] 模拟模型版本不匹配
- [ ] 模拟消息重复投递
- [ ] 验证重复事件不重复告警
- [ ] 验证降级原因可审计
- [ ] 生成 failure drill report
- [ ] 生成 incident runbook

**Phase 6 Gate Criterion：** 分析员可以在一个页面完成告警复核闭环；全链路可 replay；热路径 P95 <3s、P99 <8s；所有降级原因可审计。

---

## Phase 7 — 灰度上线与运营交接（第15-16周）

### P7-A Gray Launch

**依赖：Phase 6 完成**

- [ ] 选择 1-3 个协议灰度
- [ ] 开启 watch 告警
- [ ] 开启 high 告警
- [ ] 开启 critical 告警
- [ ] 确认不自动执行链上处置
- [ ] 配置 Dashboard 通知
- [ ] 配置 Pager/飞书通知
- [ ] 配置电话升级或人工升级路径
- [ ] 配置 SLA/SLO dashboard

### P7-B Daily and Weekly Operations

- [ ] 每日复盘误报
- [ ] 每日复盘漏报
- [ ] 每日复盘 trace failure
- [ ] 每日复盘 RAG null retrieval
- [ ] 每日复盘 high/critical 处置结果
- [ ] 每周更新 threshold profile
- [ ] 每周更新 runbook
- [ ] 每周复盘模型漂移指标
- [ ] 每周复盘标签授权和文档更新

### P7-C Operational Handoff

- [ ] 完成值班交接
- [ ] 完成升级路径确认
- [ ] 完成多签或授权负责人名单确认
- [ ] 完成 incident room 模板
- [ ] 完成 production runbook
- [ ] 完成 weekly review template
- [ ] 完成 gray launch report
- [ ] 完成 go/no-go review packet

**Phase 7 Gate Criterion：** 连续两周稳定运行；严重告警有完整图证据、审计日志和人工复核记录；上线评审通过。

---

## Go/No-Go Checklist

上线前必须全部满足：

- [ ] `pending-tx.v1 -> alert-event.v1` 全链路可 replay
- [ ] 同一输入在同一模型版本下输出稳定
- [ ] high/critical 告警具备图证据
- [ ] high/critical 告警具备 reason codes
- [ ] high/critical 告警具备审计日志
- [ ] high/critical 告警具备人工复核入口
- [ ] RAG 超时不阻塞告警
- [ ] RAG 超时原因被记录
- [ ] 主执行节点切换演练完成
- [ ] 备用执行节点切换演练完成
- [ ] 第三方 provider 切换演练完成
- [ ] 目标协议白名单已冻结
- [ ] 模型阈值已冻结
- [ ] 风险类型已冻结
- [ ] 标签授权清单已冻结
- [ ] 所有处置动作默认停留在建议交易或 runbook
- [ ] 系统不具备自动链上执行权限

---

## Validation Metrics Checklist

### 离线模型质量

- [ ] ROC-AUC ≥0.95
- [ ] PR-AUC 相对项目内基线提升
- [ ] Recall@FPR≤3% ≥0.80
- [ ] Lead time 已统计
- [ ] Calibration error 已统计

### 实时链路质量

- [ ] Pending event enqueue P95 ≤100ms
- [ ] Trace P95 ≤1.5s
- [ ] Graph build P95 ≤300ms
- [ ] Model inference P95 ≤50ms
- [ ] End-to-end detection P95 <3s
- [ ] End-to-end detection P99 <8s

### 证据与复核质量

- [ ] High/Critical graph evidence coverage = 100%
- [ ] High/Critical explanation availability = 100%，可异步补齐
- [ ] EvidenceRef validity = 100%
- [ ] Duplicate alert rate 接近 0
- [ ] Analyst review completion 全部状态留痕

---

## Explicitly Out of Scope for Phase 1

- [ ] 不做多链同时上线
- [ ] 不做自动链上处置
- [ ] 不把 Graph Transformer 作为主模型
- [ ] 不建设全量实体归因系统
- [ ] 不让 RAG 同步阻塞告警
- [ ] 不优先建设展示型大屏

---

## Immediate Next Actions

- [ ] 冻结 Ethereum 主网和首批目标协议白名单
- [ ] 搭建一主一备执行节点
- [ ] 实现 `debug_traceCall/trace_call` pending 模拟 PoC
- [ ] 创建四份 schema：`PendingTxEvent`、`TraceBundle`、`GraphInferenceRequest`、`AlertEvent`
- [ ] 用历史 exploit 和正常复杂交易构建 replay 集
- [ ] 先实现规则基线，再训练 GraphSAGE
- [ ] 建立协议文档、审计报告和 exploit postmortem 的 RAG 知识库
- [ ] 定义 high/critical 告警模板和人工复核状态机
- [ ] 完成降级演练和 go/no-go 评审后再灰度上线
