# Phase 0 On-call and Approval Runbook

**Version:** `runbook.v1`  
**Freeze date:** 2026-05-13

## Roles

| Role | Responsibility |
|---|---|
| On-call analyst | Triage watch/high/critical alerts, attach evidence, suppress obvious false positives. |
| On-call engineer | Validate trace, graph, model, and infrastructure state; prepare suggested transaction if needed. |
| Incident commander | Own critical incident coordination and final escalation path. |
| Protocol owner / partner contact | Confirm protocol-specific impact and acceptable action. |
| Multisig signer / authorized approver | Approve or reject any chain action. |

## Alert State Machine

```text
new -> triaged -> escalated -> action_prepared -> approved/rejected -> resolved
```

Every transition must record:

- operator;
- timestamp;
- reason;
- evidence references;
- linked suggested action, if any.

## Severity Handling

| Severity | Trigger | Required action |
|---|---|---|
| low | score `<0.50` | Store for replay and drift monitoring. |
| watch | score `0.50-0.75` | Analyst queue review during business hours. |
| high | score `0.75-0.90` | On-call analyst review within 10 minutes; RAG explanation must be requested asynchronously. |
| critical | score `>0.90` | Immediate page to analyst and engineer; incident commander assigned; prepare runbook and suggested transaction if relevant. |

## Critical Approval Flow

1. Analyst confirms the alert is not an obvious duplicate, replay artifact, or
   stale simulation.
2. Engineer checks trace source, `trace_status`, graph evidence, reason codes,
   model version, feature version, and provider health.
3. If a chain action is relevant, engineer prepares an unsigned transaction or
   protocol-specific action plan.
4. Incident commander requests protocol owner, multisig, or delegated approver
   review.
5. Approver signs or rejects. The system records the decision and evidence.
6. No automated signer is allowed in Phase 1-8.

## Allowed Suggested Actions

- `manual_review`
- `prepare_pause_tx`
- `raise_slippage_guard`
- `disable_borrow_entry`
- `freeze_oracle_update`
- `notify_protocol_owner`
- `open_incident_room`

Suggested actions are recommendations only. They are not execution authority.

## Third-party Label Language

Allowed:

- "Label provider reports this address with confidence 0.82."
- "This label is used as a risk signal."

Not allowed:

- "This address is legally owned by X."
- "This proves attacker identity."

