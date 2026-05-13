# Phase 0 Scope Freeze

**Project:** Real-time DeFi 价格操纵预警系统  
**Scope status:** Frozen for Phase 1 planning  
**Freeze date:** 2026-05-13  
**Owner:** Project governance group

## 1. Chain Scope

一期只覆盖 Ethereum 主网。

| Item | Decision |
|---|---|
| chain_id | `1` |
| network | Ethereum Mainnet |
| multi-chain support | Out of scope for Phase 1-8 |
| L2 support | Out of scope for Phase 1-8 |
| cross-chain bridge monitoring | Out of scope unless the Ethereum-side contract is in the target whitelist |

Multi-chain expansion requires a new Phase 0 review because mempool visibility,
trace APIs, address labels, oracle patterns, and protocol deployment addresses
are chain-specific.

## 2. Hot Path Latency Budget

The realtime detector must fit Ethereum's approximately 12-second slot cadence.

| Path segment | Phase 1 target |
|---|---:|
| pending transaction intake P95 | <= 100 ms |
| pending trace simulation P95 | <= 1.5 s |
| transfer parsing P95 | <= 150 ms |
| graph build P95 | <= 300 ms |
| model inference P95 | <= 50 ms |
| alert persistence and routing P95 | <= 100 ms |
| full hot path P95 | < 3 s |
| full hot path P99 | < 8 s |

RAG explanation is asynchronous. It must not enter P95/P99 hot path budgets and
must not block alert creation.

## 3. First Protocol Categories

The first protocol whitelist must cover the following categories:

| Category | Included in Phase 0 whitelist |
|---|---|
| AMM / DEX | Yes |
| Lending market | Yes |
| Oracle contracts | Yes |
| Router / Aggregator contracts | Yes |

Only contracts listed in `target_protocol_whitelist.md` are in scope for
protocol-specific parsing, role tagging, and first-wave alert routing.

## 4. Handling Boundary

The system does not execute automatic on-chain responses in Phase 1-8.

Critical alerts generate:

- a risk score and reason codes;
- graph evidence and trace references;
- suggested transaction templates where applicable;
- a runbook step list;
- escalation notifications.

Actual chain actions require human, multisig, or explicitly delegated owner
approval as defined in `oncall_approval_runbook.md`.

## 5. Evidence Boundary

Third-party labels and entity attribution are risk signals only. They must not
be presented as legal facts or definitive identity statements in alerts,
operator notes, or external reports.

Approved evidence reference families:

- `[GRAPH:tx_hash:edge_path]`
- `[DOC:source_id#section]`
- `[LABEL:provider:confidence]`

