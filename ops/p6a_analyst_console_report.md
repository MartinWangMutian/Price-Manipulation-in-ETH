# P6-A Analyst Console View-model Report

## Scope

Implemented the local analyst console view-model layer from replay artifacts.

## Implemented

- Alert list view model
- Alert detail view model
- Transaction basics
- Pending simulation summary
- Cash-flow graph summary
- Critical path field
- Reason codes
- Model metadata
- RAG evidence
- Label evidence
- Suggested actions
- Review state machine config
- Initial review audit trail and export

## Remaining Gap

This is not yet a rendered web console. It is the data layer that a console UI can consume.

Current validation:

- alert list items: 110
- alert detail views: 110
- review audit trail lines: 110
- review states: all `new`
- check status: ok
