# P6-C Replay Load Test Report

## Scope

Implemented replay-local load measurement for stages that can run without a live node.

## Covered

- Graph builder latency
- Rule baseline / model fallback latency
- Alert orchestrator latency
- Local pending-to-alert replay latency where timestamps are available

## Not Covered

- Live pending listener pressure
- Live trace worker pressure
- Real Geth/Erigon trace latency
- High/critical workload mix

## Current Replay-local Results

- graph builder P95: `0.009ms`
- model fallback P95: `0.009ms`
- alert orchestrator P95: `0.004ms`
- end-to-end replay timestamp P95: `92727577ms`

The end-to-end value is not a live latency SLO measurement because the pipeline artifacts were generated across separate manual replay runs.
