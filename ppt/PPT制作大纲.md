# PPT 制作大纲：基于 Cash-Flow Graph 与 GraphSAGE 的实时 DeFi 价格操纵检测与预警系统

## P1 封面

**标题**：基于 Cash-Flow Graph 与 GraphSAGE 的实时 DeFi 价格操纵检测与预警系统

**内容**
- 作者、课程/专业、日期
- 关键词：DeFi 安全、价格操纵、Mempool、Cash-Flow Graph、GraphSAGE、RAG

**视觉建议**
- 以太坊交易流 / DeFi 协议网络背景图

---

## P2 汇报目录

**内容**
1. 研究背景与问题提出
2. 国内外研究现状
3. 系统总体设计
4. Cash-Flow Graph 建模
5. 规则基线与 GraphSAGE 方案
6. 系统实现与数据分析
7. 实验结果与讨论
8. 总结与展望

---

## P3 研究背景：DeFi 价格操纵为何重要

**内容**
- DeFi TVL 高，协议间高度可组合
- 价格操纵攻击通常在单笔交易内完成
- 典型事件：bZx、Cream Finance、Mango Markets、Euler Finance
- 攻击损失巨大，且事后追踪难以追回资金

**视觉建议**
- 攻击事件时间线 + 损失金额条形图

---

## P4 问题提出：事后检测为什么不够

**内容**
- 现有系统多在交易上链后检测
- 价格操纵攻击常在一个 Ethereum slot 内完成
- 上链后再告警，资金损失通常已经发生
- 核心问题：能否在 pending 阶段提前预警？

**页面核心句**
> 能否在交易仍处于 mempool、尚未出块时完成风险识别？

---

## P5 技术挑战

**内容**

### 1. 时间约束
- Ethereum slot 约 12 秒
- 热路径目标：P95 < 3s，P99 < 8s

### 2. 信息不完整
- pending 交易可能被替换、丢弃、重排
- 私有 mempool 不可见
- pending trace 与最终上链结果不完全一致

### 3. 安全边界
- 误报造成运营负担
- 漏报造成资金损失
- 默认不自动链上处置，保留人工复核

---

## P6 文献综述：已有方法分类

**内容**

| 类型 | 代表工作 | 特点 | 局限 |
|---|---|---|---|
| 规则/语义检测 | DeFiRanger | 可解释性强 | 难发现未知攻击 |
| 图神经网络 | DeFiGuard | Cash-Flow Graph + GraphSAGE | 事后检测 |
| 商业安全服务 | CertiK / SlowMist | 覆盖广 | 方法不透明、时效偏后 |

**视觉建议**
- 横向对比表

---

## P7 与 DeFiGuard 的区别

**内容**

| 维度 | DeFiGuard | 本文 |
|---|---|---|
| 检测时机 | 已上链交易 | pending 交易 |
| 节点 | Address / Asset | + Protocol / Transaction |
| 边 | Transfer | + Call / Context |
| 退化机制 | 无 | 规则基线接管 |
| 证据解释 | 无 | EvidenceRef + RAG |

**讲解重点**
- 本文不是只增加特征，而是扩展了图拓扑结构
- Protocol 节点编码协议角色
- Call 边编码函数级语义
- Context 边编码时间窗口上下文

---

## P8 系统总体架构

**内容**

```text
pending 交易接入
        ↓
Trace 模拟 / 轻特征解析
        ↓
Cash-Flow Graph 构建
        ↓
风险评分：规则基线 / GraphSAGE
        ↓
告警与证据解释
        ↓
RAG 冷路径补充解释
```

**讲解重点**
- 热路径负责快速评分
- 冷路径负责解释，不阻塞告警
- 当前实现为 Provider-only 原型
- 完整 trace 环境作为后续扩展

---

## P9 数据接入与 Trace 层设计

**内容**
- 输入：pending transaction
- 完整方案：本地 Geth / Erigon 执行 `debug_traceCall`
- 当前原型：Provider-only，使用 Alchemy WebSocket + 轻特征解析

**Trace 状态**
- `ok`：完整 trace
- `partial`：部分字段可用
- `failed`：仅保留 raw_tx 轻特征

**核心原则**
> 宁可带着不完整信息继续检测，也不能完全不检测。

---

## P10 Cash-Flow Graph 建模

**内容**

### 节点类型
- `Address`
- `Asset`
- `Protocol`
- `Transaction`

### 边类型
- `Transfer`
- `Call`
- `Context`

**示例路径**

```text
Attacker
  → FlashLoan
  → Uniswap Pool
  → Lending Protocol
  → Attacker
```

**讲解重点**
- Transfer 边表达资金流
- Call 边表达函数调用语义
- Protocol 节点表达协议角色
- Context 边表达时间窗口上下文

---

## P11 特征工程

**节点特征**
- `account_type`
- `is_contract`
- `protocol_id`
- `contract_role`
- `pool_type`
- `has_pause`
- `profit_path_score`

**边特征**
- `amount_norm`
- `value_usd`
- `selector`
- `call_depth`
- `call_type`
- `window`
- `relation_type`

**讲解重点**
- 多资产资金流必须统一折算为 USD
- 缺失字段用 `feature_missing_flags` 显式标记
- 避免把“未知”误认为“正常”

---

## P12 规则基线评分器

**五条规则**
1. 异常利润路径检测
2. 同交易预言机读写检测
3. 闪电贷路径检测
4. 过度滑点检测
5. 薄池交易检测

**融合公式**

```text
score = min(1.0, Σ(w_i_normalized * r_i))
```

**说明**
- 配置中保留原始相对权重
- 线上运行时归一化
- 当前原型验证的是规则框架、原因码、告警链路和降级行为
- 高精度规则触发依赖完整 trace 与价格/流动性数据

---

## P13 关键算法：利润路径分析

**公式**

```text
profit_path_score =
(Σ inflow_value_usd - Σ outflow_value_usd)
/
max(1, Σ outflow_value_usd)
```

**说明**
- 用 USD 统一计价
- 闪电贷 borrow / repay 要特殊处理
- 攻击者地址通常表现为异常净流入
- 正常套利利润率通常较低

**视觉建议**
- 正常套利路径 vs 价格操纵路径对比图

---

## P14 GraphSAGE 模型设计

**定位**
- 完整 trace 环境下的在线主模型设计
- 当前 Provider-only 原型尚未训练 GraphSAGE

**模型结构**
- 两层 SAGEConv
- Mean Aggregator
- Hidden dim = 64
- Dropout = 0.1
- 输出：交易风险概率

**优势**
- 归纳式学习
- 可处理新地址、新合约
- 适合攻击者频繁更换地址的场景

**边界**
- 训练依赖完整 trace-backed 数据集
- 当前仅完成接口和退化协议预留

---

## P15 RAG 证据解释模块

**定位**
- 不参与风险评分
- 不进入热路径
- 用于高危告警的解释和证据补充

**输入证据**
- `GRAPH`：图路径证据
- `DOC`：协议文档、审计报告、攻击复盘
- `LABEL`：第三方标签，仅作风险参考

**输出**
- `graph_summary`
- `doc_summary`
- `analyst_note`

**价值**
- 提升告警可解释性
- 降低分析员复核成本
- 避免模型黑箱

---

## P16 数据集与当前实现

**当前项目实现**
- 74 个 Python 模块
- 16 个配置/模板文件
- 7 个版本化事件 Schema

**目标协议**
- Uniswap v3
- Aave v3
- Compound III
- Chainlink

**数据**
- 1,015 笔 pending 交易 replay
- 7 笔 exploit 候选
- 50 笔 normal 候选
- 57 笔 trace-ready 候选交易

**边界**
- 当前是 Provider-only 原型
- 完整 historical trace replay 尚未执行

---

## P17 实验与验证结果

**已验证内容**

| 验证项 | 结果 |
|---|---|
| pending_replay | 通过 |
| trace_audit | 通过 |
| graph_replay | 通过 |
| risk_replay | 通过 |
| alert_replay | 通过 |
| rag_explanation | 通过 |
| console_view | 通过 |
| offline_eval | 通过 |
| failure_drill | 通过 |

**重点结论**
- 1,015 笔 replay 全链路一致
- 幂等性 100%
- 故障注入全部通过

---

## P18 延迟结果与目标

**当前 Provider-only 实测**

| 管道层 | P50 | P95 |
|---|---:|---:|
| pending 接入 | 35ms | 85ms |
| tx-only 图构建 | 0.005ms | 0.008ms |
| 规则基线评分 | 0.5ms | 1.2ms |
| 端到端 | ~40ms | ~90ms |

**完整 trace 环境目标**
- P95 < 3s
- P99 < 8s

**说明**
- 当前实测不包含完整 `debug_traceCall`
- 生产级延迟仍需本地节点验证

---

## P19 结果讨论与局限性

**局限性**

### 1. Provider-only 限制
- Call 边、Context 边无法完整构建
- GraphSAGE 尚未训练

### 2. 标注数据稀缺
- exploit 样本少
- 时间外推评估尚未完成

### 3. Mempool 可见性不完整
- 私有 mempool 和 MEV relay 不可见

### 4. 自动防御不可直接上线
- 需要治理权限、多签、法律和运营流程支持

### 5. 检测性能尚未严格横向比较
- 当前以系统验证为主
- 准确率需完整 trace 数据后评估

---

## P20 总结与展望

**总结**
1. 提出 pending 阶段 DeFi 价格操纵预警系统
2. 设计 Cash-Flow Graph 增量模型：Protocol / Call / Context
3. 实现 Provider-only 可运行原型，并完成 replay、故障降级和证据解释验证

**未来工作**
- 部署 Geth / Erigon 获取完整 trace
- 完成 GraphSAGE 训练与消融实验
- 扩展多链和 L2
- 引入时序图模型二级复核
- 与 MEV 基础设施集成
- 完善人工复核与应急处置流程

**收束句**
> 本项目当前完成的是可回放、可审计、可降级的 DeFi 风险预警原型；完整 trace 与 GraphSAGE 将决定其进一步检测性能上限。
