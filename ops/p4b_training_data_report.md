# P4-B Training Data Report

## Scope

Created the seed training data manifest flow for Phase 4-B.

## Implemented

- Public positive incident seed file
- Split policy with train/validation/replay ratios
- Provider-only unlabeled pool construction
- Deterministic train/validation/replay split manifests
- Label snapshot with blocking reasons
- Replay label candidate backlog for exploit transaction review

## Seed Sources

The seed file includes public incident/postmortem/security-report references for Euler Finance, Beanstalk Farms, Cream Finance, Harvest Finance, bZx, Mango Markets, Curve/Vyper, and Conic Finance.

## Current Status

The dataset is not training-ready. It is an auditable label seed and split manifest.

Current builder output:

- positive incident seeds: 8
- train/validation/replay split counts: 6 / 1 / 1
- provider-only unlabeled graphs: 110
- candidate transaction hashes: 7
- incidents missing key transaction review: 1
- `training_ready`: false
- dataset check status: ok

Candidate transaction hashes still need replay against real trace data and analyst promotion before they can become confirmed training labels.

## Blocking Gaps

- Candidate transaction hashes require trace replay and some require secondary source review
- Current local graphs are provider-only and cannot be used as confirmed negatives
- Stratified negative samples require rich graph features by protocol, time period, and transaction complexity
