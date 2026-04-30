---
type: decision
domains: [meta]
created: 2026-04-29
updated: 2026-04-30
sources: []
summary_l0: "Généralisation frames vidéo : modes A/B pour tous agents experts, scripts packagés, transcription markdown obligatoire"
summary_l1: |
  La décision unifie la capacité d'extraction vidéo sur tous les agents via deux modes complémentaires : mode A léger (« frame requests » déclarées par l'agent) pour vidéos pauvres en visuel, mode B lourd (induction croisée en 9 étapes) pour vidéos denses. Le main context propose dynamiquement le mode adapté selon densité et durée. Chaque agent reçoit une section « Frames visuelles » avec déclencheurs verbaux domaine-spécifiques. Scripts d'extraction packagés (sample-frames.sh, diff-frames.py). Toute frame promue doit être transcrite en markdown pour rendre le contenu queryable sans re-vision.
---
# Décision — Généralisation `/ingest-video` & extraction de frames à tous les agents

## Problème

Avant cette décision, deux pipelines d'extraction de frames vidéo coexistaient mais aucun n'était utilisable proprement par les agents experts :

1. **Mode léger ("frame requests")** — l'agent déclare des timestamps depuis le transcript via un bloc `## Frame requests`. Implémenté dans [.claude/commands/ingest-video.md](../../.claude/commands/ingest-video.md). Section `## Frames visuelles` historiquement absente chez la plupart des agents.

2. **Mode lourd ("induction croisée")** — pipeline en 8 étapes documenté dans [[decisions/extraction-frames-induction-runbook]]. Aucune intégration dans `/ingest-video`, aucun script packagé (commandes ffmpeg/Python en inline dans le runbook), runbook initialement orienté un seul cas d'usage.

Conséquences :
- Plusieurs agents ne pouvaient rien capter de visuel sur leurs vidéos.
- Le mode lourd restait un sous-cas, alors que des vidéos denses en visuels existent dans tous les domaines (démos logicielles, captures d'outils, dashboards, schémas).
- Pas d'outillage pour reproduire le mode lourd hors du contexte d'un humain qui copie-colle des commandes ffmpeg.
- **Frames orphelines** : une frame promue sans transcription markdown oblige les futures `/query` à ré-analyser l'image à chaque appel — coût récurrent, perte d'indexation grep/search.

## Options écartées

- **Mode lourd seulement, abandonner le mode léger** : on perdrait le réflexe simple « 2-4 frames sur talk de 1 h » sans devoir lancer un pipeline en 8 étapes. Trop coûteux pour des vidéos pauvres en visuel.
- **Mode léger seulement, ne pas généraliser le mode lourd** : on garderait la sous-extraction systématique sur les vidéos denses (≥30 min, ≥10 visuels).
- **Auto-trigger silencieux du mode A vs B** : le main context bascule sans demander. Risqué — investit du compute lourd sur des vidéos qui ne le valaient pas, ou rate des frames en restant sur mode léger.
- **`AskUserQuestion` systématique avant chaque vidéo** : ajoute une interruption à chaque ingest, même sur des podcasts évidents.

## Décision retenue

### A. Les deux modes coexistent et sont utilisables par tous les agents

- **Mode A (léger, frame requests)** : section `## Frames visuelles` insérée dans tous les prompts d'agents experts générés depuis le template, avec déclencheurs verbaux propres au domaine.
- **Mode B (lourd, induction croisée)** : runbook [[decisions/extraction-frames-induction-runbook]] *domain-agnostic*, particularités domaine en **Annexes domaine**. Le pipeline est piloté par `/ingest-video` et le main context, pas par l'agent — donc aucun prompt d'agent ne change pour le mode B.

### B. `/ingest-video` propose le mode adapté, l'utilisateur tranche

Après transcription + ingest standard, `/ingest-video` calcule des signaux (durée, densité de mentions visuelles dans le transcript, nombre de frames demandées par l'agent) et propose A / B / Skip via `AskUserQuestion` avec une recommandation justifiée. Pas d'auto-trigger silencieux. Overrides explicites disponibles : `--induction`, `--mode-a`, `--skip-frames`.

### C. Scripts du pipeline lourd packagés

- [scripts/sample-frames.sh](../../scripts/sample-frames.sh) : sampling dense ffmpeg avec cadence paramétrable (défaut 20 s).
- [scripts/diff-frames.py](../../scripts/diff-frames.py) : image-diff ROI optionnel (défaut plein cadre `0,0,1,1`), seuil paramétrable, sortie markdown des transitions.

### D. Transcription markdown obligatoire après promotion (Étape 9 du runbook)

Chaque frame promue (mode A comme mode B) **doit** être transcrite en markdown structuré dans la page wiki qui la consomme — pour rendre le contenu interrogeable par `/query` sans re-vision. Format selon le type de visuel (tableau / Mermaid / code / liste KPIs / description sémantique). Une frame sans transcription markdown est un défaut d'ingest.

## Pourquoi

- **Cohérence wiki** : tous les agents avec la même primitive frames, sinon les domaines hors du sous-cas d'origine resteraient aveugles.
- **Respect du coût** : le mode B vaut son investissement uniquement sur des vidéos suffisamment denses ; la proposition utilisateur évite la sur-extraction silencieuse.
- **Pas de défaut implicite douteux** : ROI plein cadre par défaut, pas de géométrie spécifique imposée à toutes les vidéos.
- **Index queryable** : la transcription markdown au moment de la promotion paie immédiatement à chaque `/query` future. Sans elle, on accumule de la dette d'indexation.

## Périmètre des changements

| Fichier | Action |
|---|---|
| [[decisions/extraction-frames-induction-runbook]] | Réécriture domain-agnostic + Annexes domaine (squelettes vides à enrichir au fil des ingests) + Étape 9 |
| `.claude/agents/<domain>-expert.md` (tous) | Section `## Frames visuelles` (mode A) avec déclencheurs domaine + transcription markdown obligatoire |
| [scripts/sample-frames.sh](../../scripts/sample-frames.sh), [scripts/diff-frames.py](../../scripts/diff-frames.py) | Packagés dans le template |
| [.claude/commands/ingest-video.md](../../.claude/commands/ingest-video.md) | Dispatcher A/B (proposition utilisateur) + branche pipeline mode B |
| [CLAUDE.md](../../CLAUDE.md) | Section INGEST-VIDEO mise à jour |
| `wiki/domains/<d>.md` | Cross-ref vers le runbook |

## Questions ouvertes

- **Affiner les déclencheurs verbaux par domaine** : les listes initiales (insérées dans chaque agent au bootstrap) sont des propositions de départ. Elles doivent évoluer avec les premières ingestions vidéo dans chaque domaine.
- **Annexes domaine du runbook** : aujourd'hui des squelettes. À enrichir au fil des ingests réels (pas d'invention prématurée).
- **Performance transcription markdown** : un agent expert est-il toujours capable de transcrire fidèlement un schéma complexe ? À mesurer sur des cas réels et ajuster (peut-être un livrable spécialisé pour les diagrammes complexes).
- **Mode batch full-multiSelect Étape 6** : sur des batchs de 50+ frames sans ambiguïté, un mode batch sans question par frame serait acceptable. À tester.

## Cross-réfs

- [[decisions/extraction-frames-induction-runbook|Runbook induction croisée]] (le pipeline lourd lui-même)
