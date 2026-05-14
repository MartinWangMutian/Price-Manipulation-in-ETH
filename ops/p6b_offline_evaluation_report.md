# P6-B Replay and Offline Evaluation Report

## Scope

Implemented the local replay/evaluation reporting layer from current replay artifacts.

## Implemented

- Historical exploit replay seed set
- Provider-only unlabeled evaluation set
- `pending-tx.v1 -> alert-event.v1` replay count reporting
- Threshold distribution reporting
- High/critical graph evidence coverage metric
- High/critical explanation availability metric
- EvidenceRef validity metric
- Offline evaluation report
- Threshold calibration report

## Remaining Gap

False positives, false negatives, lead time, and true threshold calibration require confirmed exploit replay and normal complex transaction sets.

## Current Validation

- alerts replayed: 110
- risk scores: 110
- graphs: 110
- exploit replay seed incidents: 8
- provider-only unlabeled evaluation txs: 110
- EvidenceRef validity: 550 / 550
- severity distribution: `low=110`
- threshold report generated with `calibration_ready=false`
