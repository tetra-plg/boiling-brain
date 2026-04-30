---
type: decision
domains: [meta]
created: 2026-04-29
updated: 2026-04-29
sources: []
summary_l0: "Tiered loading wiki : summary_l0 (≤140 chars) + summary_l1 (2-5 phrases) pour oracles domaine optimisés."
summary_l1: |
  Décision d'ajouter deux champs frontmatter (summary_l0 ≤140 chars, summary_l1 2-5 phrases) pour un tiered loading natif du wiki. Les agents experts chargeront d'abord un TOC rapide (L0), puis des previews (L1), avant le body complet (L2). Cela permet aux oracles éventuels de charger un domaine entier sans relire chaque page en entier. Agents experts produisent ces champs à l'ingest ; pages existantes sont complétées par un script batch idempotent.
---
# Tiered loading dans le frontmatter du wiki

## Le problème

Les agents experts (poker-expert, ia-expert, etc.) doivent **maîtriser** la base de connaissance de leur domaine — pas seulement savoir y écrire. À chaque invocation, l'agent se base essentiellement sur `wiki/domains/<d>.md` pour découvrir ce qui existe ; au-delà il doit lister/lire au cas par cas.

Deux limites apparaissent :

1. **Coût et lenteur** : pour répondre à une question transversale (ex. « fais-moi un plan d'étude X »), l'agent doit lire de nombreuses pages — beaucoup pour rien si la pertinence n'est pas évidente depuis le titre.
2. **Oracle par domaine** (pattern de scaling éventuel) : on veut charger le wiki d'un domaine entier dans un contexte large. Sans structure tiered, on charge tout en L2 (full body) et on consomme inutilement du contexte sur des pages dont seul le titre était pertinent.

On veut un mécanisme de tiered retrieval directement dans le frontmatter du wiki — versionné, lisible, sans dépendance à un provider externe.

## Les options écartées

**Option A — Index séparé `wiki/domains/<d>-index.md`.**
Doublon de `domains/<d>.md`. Risque de drift entre les deux.

**Option B — Provider externe d'embeddings (RAG vectoriel).**
Coût d'infrastructure, perte de l'aspect « knowledge compilation » Karpathy (la base reste compacte et lisible). Sur-dimensionné pour un wiki de quelques centaines de pages.

**Option C — Provider de mémoire externe.**
Le tiered loading est résolu côté provider mais pas côté Claude Code (orchestrateur). Et nécessite de structurer la base d'une manière propre à ce provider.

## La décision retenue

**Ajouter deux champs frontmatter optionnels-recommandés** sur les pages du wiki, et utiliser ces champs comme structure de tiered loading native :

```yaml
---
type: cheatsheet
domains: [<domain>]
summary_l0: "Résumé télégraphique en une ligne ≤140 chars"
summary_l1: |
  Description structurée 2-5 phrases (~50-150 mots) du contenu.
  Couvre les points saillants sans dupliquer le body.
created: YYYY-MM-DD
---
```

### Spécification

- **`summary_l0`** : ≤140 caractères. **Une seule ligne**, ton télégraphique. Sert de TOC quand un agent scanne un domaine entier.
- **`summary_l1`** : 2-5 phrases (~50-150 mots). Description structurée. Sert quand l'agent doit décider s'il lit le body L2.
- **Body** : la page elle-même (= L2, contenu actuel inchangé).

### Trois usages

1. **Hub `wiki/domains/<d>.md`** régénéré comme TOC L0 navigable : chaque entrée du hub = `[[lien]] — summary_l0`. L'agent lit le hub en quelques milliers de tokens et sait où aller.
2. **Oracle par domaine** : pré-charge tous les `summary_l1` d'un domaine en contexte (~30K tokens pour 100 pages). Pour une question donnée, ne charge en L2 que les 2-5 pages réellement pertinentes.
3. **Subagent expert quotidien** : reçoit dans son prompt système le hub L0 + summary_l1 des concepts structurants de son domaine. Au lieu de redécouvrir, il navigue.

### Qui les écrit

- **Pour les pages nouvelles** : l'agent expert produit `summary_l0` et `summary_l1` à l'ingest. Cette exigence est dans le prompt système de chaque agent expert.
- **Pour les pages existantes** : `scripts/backfill-summaries.py` parcourt `wiki/**/*.md`, identifie les pages sans `summary_l0`, invoque Claude Code pour produire les deux champs, applique l'edit. Tourne en mode batch, idempotent (skip les pages déjà munies).

### Pourquoi `l0` et `l1` plutôt que d'autres noms

- Pas de connotation domaine ("titre" est ambigu, "abstract" trop scientifique).
- Numérique → permet d'ajouter un `l2` un jour si on voulait stocker un body compressé.

## Ce que ça débloque

- **Hub `wiki/domains/<d>.md`** devient lisible humainement (table des matières) ET machinement (un agent lit 4-5 K tokens et a la cartographie complète).
- **Oracle par domaine** devient économiquement viable.
- **Détection de redondance** : deux pages avec des `summary_l0` proches signalent un risque de doublon que `/lint` peut remonter.
- **Cross-domain queries** : un script peut charger les `summary_l0` de tous les domaines (~5K tokens total) pour répondre aux questions transversales.

## Questions ouvertes

- **Régénération automatique** quand le body d'une page change-t-il significativement ? Politique : laisser à l'humain via `/evolve-agent` ou `/lint`. Pas d'auto-rewrite des summaries (risque de drift).
- **Format de `summary_l1`** : free-text ou structuré (sections nommées) ? Choix : free-text au démarrage, structurer si patterns émergent.
- **Pages très courtes** (< 50 lignes) : faut-il imposer `summary_l0` ? Réponse : oui par cohérence, le coût est nul.

## Fichiers à produire

- `scripts/backfill-summaries.py` — backfill batch idempotent (fourni dans le template).
- Mise à jour de `CLAUDE.md` section « Conventions » : ajouter les deux champs au frontmatter type.
- Mise à jour des prompts d'agents experts (`.claude/agents/<x>-expert.md`) : exigence d'écrire `summary_l0` et `summary_l1` à chaque ingest.
