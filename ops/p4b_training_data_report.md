# P4-B Training Data Report

## Scope

Created the seed training data manifest flow for Phase 4-B.

## Implemented

- Public positive incident seed file
- Split policy with train/validation/replay ratios
- Provider-only unlabeled pool construction
- Deterministic train/validation/replay split manifests
- Label snapshot with blocking reasons

## Seed Sources

The seed file includes public incident/postmortem/security-report references for Euler Finance, Beanstalk Farms, Cream Finance, Harvest Finance, bZx, Mango Markets, Curve/Vyper, and Conic Finance.

## Current Status

The dataset is not training-ready. It is an auditable label seed and split manifest.

Current builder output:

- positive incident seeds: 8
- train/validation/replay split counts: 6 / 1 / 1
- provider-only unlabeled graphs: 110
- incidents missing key transaction review: 7
- `training_ready`: false
- dataset check status: ok

Most positive incidents still need transaction hash review and replay against real trace data.

## Blocking Gaps

- Key transaction hashes are missing for most incidents
- Current local graphs are provider-only and cannot be used as confirmed negatives
- Stratified negative samples require rich graph features by protocol, time period, and transaction complexity
