---
type: decision
domains: [<domain1>]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
status: pending              # pending | accepted
verdict: null            # null | validated | invalidated | partial — fill after T+30/60/90d
verdict_date: null       # YYYY-MM-DD when verdict was assigned
verdict_evidence: null   # short text: what actually happened
revisit_after: null      # optional YYYY-MM-DD — /lint flags this page when the date is past
summary_l0: "≤140 chars"
summary_l1: |
  2-5 sentences.
---

# ADR — <title>

## Problem

<What forced this decision? Constraints, observations, evidence.>

## Discarded options

<Other paths considered and why they were dropped.>

## Decision

<The chosen path, in one paragraph.>

## Why

<Rationale, trade-offs, dependencies.>

## Open questions

- [ ] <Question to revisit later.>

## Real feedback

<!-- Fill 30/60/90 days after the decision. Empty = ADR not yet validated by reality.
     Mechanism: `/lint` flags ADRs ≥90d old without `verdict`. -->

### YYYY-MM-DD (T+Xd)

- What happened:
- Hypothesis confirmed / invalidated:
- Revision action:
