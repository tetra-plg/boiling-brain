---
description: Ingest sources from raw/ into the wiki via un agent expert de domaine (batch, idempotent, hash-based)
argument-hint: [--force] [--frames] [chemin-ou-dossier — vide = tout raw/]
---

Run the INGEST workflow from CLAUDE.md on: $ARGUMENTS

**Mode batch idempotent.** Comportement :
- Sans argument → scan complet de `raw/`.
- Argument = dossier → scan du sous-arbre.
- Argument = fichier → force re-ingest **de ce fichier uniquement**.
- Flag `--force` (combinable avec dossier ou scan global) → traite chaque fichier comme **modifié**, même si le sha256 est inchangé. Utile après une évolution d'agent expert (`/evolve-agent`) pour bénéficier des nouveaux réflexes sur des sources déjà ingérées. **Aucune création de doublon** : le re-ingest met à jour les pages existantes (sources, entités, concepts) plutôt que d'en créer de nouvelles avec des slugs différents.
- Flag `--frames` (combinable avec `--force` et un fichier/dossier) → indique à l'agent que l'objectif est d'**extraire les frames visuelles manquantes**. L'agent doit relire le transcript, produire un bloc `## Frame requests` selon la convention, et ne rien modifier d'autre dans les pages existantes. Utilisable seul (`--frames`) ou combiné (`--force --frames`) sur un transcript déjà ingéré.

Pour chaque fichier du scope, depuis le **main context** :

### 1. Détection de l'état

Lancer `bash scripts/scan-raw.sh [scope]` (sans argument = tout `raw/` ; avec dossier ou fichier = sous-arbre). Le script produit une ligne par fichier :

```
NEW      raw/...    → jamais vu
SKIP     raw/...    (covered-by: <slug>)   → déjà couvert par une page wiki
MODIFIED raw/...    (covered-by: <slug>, sha-changed)   → couvert mais contenu modifié
```

La détection est **robuste** : elle cherche correspondance exacte sur `source_path`, puis sur `covered_paths` (liste de tous les raw paths couverts par une page composite), puis sur répertoire parent. Cela évite les faux "NEW" quand un agent a synthétisé plusieurs fichiers en une page sans lister chaque fichier individuellement.

Arbitrage :
- `SKIP` → ignorer (sauf si `--force` → traiter comme `MODIFIED`).
- `NEW` / `MODIFIED` → passer à l'étape 2.

**Mode `--force`** : signaler explicitement à l'agent expert dans son prompt que la source a **déjà été ingérée** (citer la page source existante) et qu'il s'agit d'un re-ingest **additif**. L'agent doit lire les pages existantes, identifier ce qui manque, ajouter uniquement ça, ne pas réécrire le contenu déjà correct. Mettre à jour `ingested:` uniquement si du contenu a été ajouté.

**Mode `--frames`** : signaler à l'agent que l'objectif est **exclusivement** de produire des frame requests pour ce transcript. Instruction au spawn :
- Relire le transcript source.
- Produire un bloc `## Frame requests` selon la convention du vault (cf. CLAUDE.md).
- **Ne rien modifier d'autre** dans les pages existantes — pas de mise à jour du contenu textuel, pas de `ingested:` mis à jour.
- Si aucun visuel détectable dans le transcript → répondre « aucune frame à déclarer » et ne pas produire le bloc.

Si vidéo/audio/URL non transcrit → enchaîner `scripts/transcribe.sh` d'abord.

### 2. Proposition d'agent expert (validation utilisateur)

**L'ingest est délégué à un agent expert du domaine.** Le main context n'écrit pas les pages — il dispatche.

1. Analyse la source : titre, emplacement dans `raw/`, extrait du contenu (~200 lignes), cross-ref avec `wiki/domains/`.
2. Propose un ou plusieurs agents experts parmi ceux présents dans `.claude/agents/` (chaque domaine déclaré au bootstrap a son `<domain>-expert.md`) avec **niveau de confiance** et **justification courte**.
3. Demande validation via `AskUserQuestion` :
   - **Confiance haute** → option « Recommandé » par défaut + 2-3 alternatives + « autre ».
   - **Confiance faible / ambiguë** → liste des experts disponibles sans recommandation + « autre ».
   - **Cross-domaine évident** → multiSelect pour lancer plusieurs experts en parallèle.
4. Si le user choisit « autre » ou personnalise, honorer son choix.

### 3. Spawn de l'agent expert

Pour chaque agent validé, lancer un appel `Agent` avec :
- `subagent_type`: l'agent choisi.
- **Prompt** contenant :
  - Chemin du fichier raw à ingérer.
  - Liste des titres des pages existantes du domaine (`wiki/entities/`, `wiki/concepts/`, `wiki/cheatsheets/`, etc. selon les livrables de l'agent).
  - Chemin de `wiki/domains/<d>.md`.
  - Instruction : exécuter l'ingest de bout en bout, puis renvoyer le rapport dans le format `## Ingest summary` + `## Evolution suggestions` (cf. prompt de l'agent).

Cross-domaine → plusieurs agents en parallèle (même appel multi-tools).

### 4. Collecte et journalisation

Quand le ou les agents ont rendu leur rapport :

1. Ajouter une entrée dans `wiki/log.md` :
   ```
   ## [YYYY-MM-DD] ingest | <titre source> (agent: <nom>)
   <résumé du bloc Ingest summary — pages créées/mises à jour, livrables>
   ```
2. Appendre le bloc `## Evolution suggestions` au fichier `.claude/agents/<domain>-expert.suggestions.md` (créer si besoin) avec un horodatage `### [YYYY-MM-DD HH:MM] source: <chemin>`.
3. Mettre à jour `wiki/index.md` si l'agent ne l'a pas déjà fait.

### 4b. Extraction de frames (si présent)

Si le rapport de l'agent contient un bloc `## Frame requests`, traiter **avant** le rapport final :

1. Vérifier si une vidéo source est disponible dans `cache/videos/` (chercher un fichier dont le nom correspond au slug du transcript ingéré).
2. Si vidéo disponible :
   a. Pour chaque ligne `FRAME: HH:MM:SS | slug | description` : extraire via `./scripts/extract-frames.sh <video_path> <timestamp> cache/frames/<slug>.png` (applique un offset de +5s par défaut — compense le décalage entre mention verbale et affichage visuel).
   b. Afficher toutes les frames extraites à l'utilisateur en un seul batch (`AskUserQuestion`).
   c. Sur validation → `cp cache/frames/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
   d. Sur rejet → proposer 3 alternatives rapides sans redemander à l'utilisateur de spécifier un offset : extraire à T-10s (`offset=-5`), T+0s (`offset=0`) et T+20s (`offset=15`) via `./scripts/extract-frames.sh <video> <timestamp> cache/frames/<slug>-altN.png <offset>`, afficher les 3 en batch, valider ou annoter `> [!question] Frame non extraite` si aucune ne convient.
3. Si aucune vidéo en cache : signaler à l'utilisateur les timestamps déclarés avec la description attendue — il peut relancer manuellement ou annoter les frames comme `> [!question]`.
4. Inclure dans le rapport final : `Frames : N promues · M rejetées` (ou `Frame requests : N déclarées — vidéo non disponible en cache`).

### 5. Rapport final global

Format :
```
N nouveaux · M mis à jour · K inchangés (skipped) · L orphelins
```
Suivi de :
- Pour chaque source : agent invoqué, pages touchées, livrables produits.
- Suggestions d'évolution remontées (pointeur vers les fichiers `.suggestions.md`).
- Contradictions détectées (entre sources ou avec le wiki existant).
- Questions ouvertes pour l'utilisateur.
- Orphelins (pages `wiki/sources/` dont le raw a disparu — pas de suppression auto).

## Notes

- Un source = un agent principal (même si cross-domaine, un agent a le lead pour la page `wiki/sources/` ; les autres enrichissent concepts/entities de leur domaine).
- Si aucun agent expert n'est adapté et que le user choisit « autre » → le main context fait l'ingest générique (fallback comportement actuel).
- Si la commande `/evolve-agent <domain>` existe, elle consomme les `.suggestions.md` pour faire évoluer le prompt de l'agent.
