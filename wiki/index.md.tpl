---
type: index
updated: {{bootstrap_date}}
---

# Index

Portail d'entrée du wiki. **L'humain entre par 3-4 points clés ; les agents (et toi en `/query`) naviguent ensuite via les hubs de domaine et les `[[wikilinks]]`.** Ce fichier reste volontairement minimal — la structure détaillée vit dans les hubs `wiki/domains/<d>.md`.

## Vue d'ensemble

- [[overview]] — Portrait de {{name}} : parcours, rôle, centres d'intérêt.
- [[radar]] — Questions ouvertes & points d'attention. Consulte-le le matin.
- [[log]] — Journal chronologique des actions sur le wiki (ingest, query, save, lint, evolve).

## Domaines

{{domains_index_section}}

---

Tout le reste (entités, concepts, sources, syntheses, cheatsheets, diagrams, decisions) est navigable via les hubs de domaine et les `[[wikilinks]]`. Ce wiki suit le pattern **tiered loading** : chaque page porte un `summary_l0` (≤140 chars) et un `summary_l1` (2-5 phrases) dans son frontmatter, ce qui permet à un agent de scanner un domaine entier sans charger les bodies. Cf. [[decisions/tiered-loading-wiki]].
