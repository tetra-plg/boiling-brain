---
type: domain
domains: [{{domain_slug}}]
created: {{bootstrap_date}}
updated: {{bootstrap_date}}
sources: []
summary_l0: "{{summary_l0}}"
summary_l1: |
  {{summary_l1}}
---
# Domain — {{domain_label}}

Hub for the **{{domain_label}}** domain.{{hub_pivot_marker}}

{{domain_intro_paragraph}}

## Sub-themes (to populate)

{{taxonomy_section}}

## Related entities

_(to populate as ingests come in)_

## Related concepts

_(to populate as ingests come in)_

## Sources

_(to populate as ingests come in)_

## Video tooling

- [[decisions/extraction-frames-induction-runbook|Frame-extraction-by-cross-induction runbook]] — 9-step pipeline invokable via `/ingest-video --induction` for visually dense {{domain_slug}} videos.
- [[decisions/ingest-video-modes-a-b-generalisation|`/ingest-video` modes A/B]] — `/ingest-video` proposes the light mode (frame requests) or the heavy mode (cross-induction) based on visual density.

{{related_domains_section}}
