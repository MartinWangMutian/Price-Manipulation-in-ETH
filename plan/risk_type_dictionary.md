# Phase 0 Risk Type Dictionary

**Version:** `risk-types.v1`  
**Freeze date:** 2026-05-13

## Naming Rules

Reason codes use lowercase snake_case.

Format:

```text
<risk_family>.<signal_name>
```

Examples:

- `oracle_manipulation.oracle_read_write_same_tx`
- `thin_liquidity_swap.pool_depth_below_floor`
- `flash_loan_price_pump.flash_loan_funded_profit_path`

Reason codes must be stable once emitted. If semantics change, create a new
code and deprecate the old code.

## Phase 1 Risk Types

| risk_type | Definition | Typical signals | Default severity floor |
|---|---|---|---|
| `oracle_manipulation` | Transaction attempts to move or exploit a price source used by a dependent protocol. | oracle read/write in same transaction, stale feed interaction, TWAP-sensitive pool movement, downstream borrow/liquidation after price movement | high |
| `flash_loan_price_pump` | Flash liquidity is used to distort price, liquidity, or collateral state within one transaction or bundle window. | flash loan source, large temporary notional, near-zero net capital, profit path back to initiator | high |
| `thin_liquidity_swap` | Swap materially moves a low-liquidity or concentrated-liquidity pool and creates exploitable reference prices. | pool depth below floor, price impact above threshold, concentrated tick exhaustion, abnormal slippage | watch |
| `sandwich_assisted_manipulation` | Transaction appears to manipulate price with adjacent pending transactions or bundle position support. | same pair before/after tx, attacker-linked address cluster, adverse price path, MEV-relative ordering signal | watch |
| `cross_protocol_liquidation_cascade` | Price movement or oracle effects produce liquidation or bad-debt risk across lending markets. | collateral price drop, liquidation calls, multiple protocol touch points, health factor collapse | high |

## Initial Reason Codes

| reason_code | risk_type | Meaning |
|---|---|---|
| `oracle_manipulation.oracle_read_write_same_tx` | `oracle_manipulation` | The transaction both changes a price-sensitive state and reads a related oracle or derived price. |
| `oracle_manipulation.downstream_lending_use` | `oracle_manipulation` | The manipulated price path is followed by borrow, repay, collateral, or liquidation activity. |
| `flash_loan_price_pump.flash_loan_funded_profit_path` | `flash_loan_price_pump` | Flash liquidity funds a path that returns profit to the initiator or linked address. |
| `flash_loan_price_pump.temporary_notional_spike` | `flash_loan_price_pump` | Transaction notional is materially above the address and pool baseline within the context window. |
| `thin_liquidity_swap.pool_depth_below_floor` | `thin_liquidity_swap` | Target pool liquidity is below the configured minimum for safe price reference use. |
| `thin_liquidity_swap.price_impact_above_threshold` | `thin_liquidity_swap` | Simulated swap price impact exceeds the per-asset or per-pool threshold. |
| `sandwich_assisted_manipulation.adjacent_conflicting_swaps` | `sandwich_assisted_manipulation` | Nearby pending transactions trade the same pair in a pattern consistent with price assistance. |
| `sandwich_assisted_manipulation.linked_sender_cluster` | `sandwich_assisted_manipulation` | Sender, funder, or beneficiary overlaps with a known or inferred address cluster. |
| `cross_protocol_liquidation_cascade.multi_market_liquidation_path` | `cross_protocol_liquidation_cascade` | The path touches multiple lending markets or liquidation modules after price movement. |
| `cross_protocol_liquidation_cascade.health_factor_collapse` | `cross_protocol_liquidation_cascade` | Simulation indicates a collateral account moves from safe to liquidatable. |

## Handling Rules

| Severity | Score interval | Default action |
|---|---:|---|
| low | `<0.50` | Log only for training, drift, and replay. |
| watch | `0.50-0.75` | Queue in analyst console. |
| high | `0.75-0.90` | Trigger RAG, create review task, notify on-call engineer. |
| critical | `>0.90` | Generate suggested transaction/runbook and escalate for approval. |

No risk type in `risk-types.v1` authorizes automatic on-chain execution.

