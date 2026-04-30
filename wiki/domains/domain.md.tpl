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
# Domaine — {{domain_label}}

Hub du domaine **{{domain_label}}**.{{hub_pivot_marker}}

{{domain_intro_paragraph}}

## Sous-thèmes (à peupler)

{{taxonomy_section}}

## Entités liées

_(à peupler au fil des ingests)_

## Concepts liés

_(à peupler au fil des ingests)_

## Sources

_(à peupler au fil des ingests)_

## Outillage vidéo

- [[decisions/extraction-frames-induction-runbook|Runbook extraction de frames par induction croisée]] — pipeline en 9 étapes invocable via `/ingest-video --induction` pour les vidéos {{domain_slug}} denses en visuels.
- [[decisions/ingest-video-modes-a-b-generalisation|Modes A/B `/ingest-video`]] — `/ingest-video` propose mode léger (frame requests) ou mode lourd (induction croisée) selon la densité visuelle.

{{related_domains_section}}
