# {{vault_name}} — Schéma du wiki personnel

Ce vault est un **LLM Wiki** : un écosystème de connaissances maintenu par LLM, centré sur l'utilisateur ({{name}}) et ses domaines d'intérêt.

## Rôles

- **Humain** : curate les sources, pose les questions, guide l'analyse.
- **LLM (toi)** : lis, synthétise, cross-référence, maintiens. Tu n'inventes pas — tu t'appuies sur les sources citées.

## Architecture

```
.claude/
  agents/        # subagents Claude Code — un expert par domaine (+ suggestions accumulées pour l'évolution)
  agent-memory/  # mémoires inter-sessions par agent (état du domaine, patterns en attente)
  commands/      # slash commands (/ingest, /ingest-video, /query, /save, /lint, /evolve-agent{{slash_commands_extras}})


raw/                 # sources brutes IMMUTABLES — ce qui est référencé par le wiki.
  notes/             # retours d'expérience perso (texte)
  transcripts/       # transcripts de vidéos/audios (YYYY-MM-DD-slug.md + timestamps)
  videos-meta/       # pointeurs/metadata des vidéos (YYYY-MM-DD-slug.meta.md : URL, durée, hash, emplacement)
  frames/            # frames extraites effectivement utilisées par le wiki (promues depuis cache)
{{tracked_repos_arborescence}}  # + articles/, pdfs/, clippings/... selon besoin

cache/                 # artefacts TRANSITOIRES — jamais référencés par le wiki, purgeables à tout moment.
  videos/              # vidéos téléchargées/déposées, supprimées après transcription
  audio/               # audio extrait, supprimé après transcription
  frames/              # frames candidates, promues vers raw/frames/ si utilisées
{{tracked_repos_cache}}
wiki/          # pages générées par le LLM. Tu possèdes cette couche.
  index.md     # portail humain minimal (overview, radar, log, domaines)
  log.md       # journal chronologique (ingest, query, lint, evolve)
  radar.md     # questions ouvertes & points d'attention — alimenté à chaque ingest, consulté chaque matin
  overview.md  # portrait de l'utilisateur, mis à jour au fil de l'eau
  domains/     # pages racines des grands domaines (hubs)
  entities/    # personnes, entreprises, produits, lieux
  concepts/    # idées, théories, frameworks
  sources/     # une page par source ingérée (YYYY-MM-DD-slug.md)
  syntheses/   # réponses substantielles archivées
  decisions/   # choix d'architecture du vault lui-même (ADR-lite)
  cheatsheets/ # tableaux synthétiques, paliers, matrices
  diagrams/    # diagrammes Mermaid / ASCII

scripts/       # utilitaires (extraction audio, transcription, sampling de frames, image-diff, backfill summaries, hub enrichment{{tracked_repos_scripts_extras}})
```

### Principe raw vs cache

- **`raw/` = strictement immutable et référencé par le wiki.** Inclut les transcripts (source de vérité pour les vidéos) et la metadata, pas les médias eux-mêmes. Chaque snapshot est un répertoire nouveau, **jamais réécrit**. Aucune exception.
- **`cache/` = transitoire.** Les vidéos, audios et clones git y passent le temps du traitement, puis sont supprimés ou archivés hors vault. Ne jamais référencer `cache/` depuis une page du wiki.
- **Conséquence** : si une frame d'une vidéo est utilisée par une page, elle doit être **promue** de `cache/frames/` vers `raw/frames/` — sinon elle disparaîtra.

## Domaines de l'utilisateur

{{domains_section}}

Chaque domaine a une page dans `wiki/domains/` qui sert de hub.

## Conventions

- Tous les liens internes sont en `[[wikilinks]]` style Obsidian.
- Pages nommées en `kebab-case.md`, titres en français.
- Frontmatter YAML sur chaque page du wiki :
  ```yaml
  ---
  type: entity | concept | source | domain | synthesis | decision | overview | cheatsheet
  domains: [<domain1>, <domain2>, ...]
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  sources: [[source-slug]]
  summary_l0: "≤140 chars, télégraphique, scannable"     # obligatoire pour domains/cheatsheets/concepts/syntheses, recommandé pour sources/entities
  summary_l1: |                                            # 2-5 phrases, ~50-150 mots, description structurée
    Description multi-lignes du contenu.
  ---
  ```
  Les champs `summary_l0` et `summary_l1` alimentent le **tiered loading** des oracles par domaine. Un agent peut scanner un domaine entier via les `summary_l0` (TOC L0) sans charger les bodies, puis descendre en L1 (preview) ou L2 (full body) seulement quand pertinent.
- Sources : `wiki/sources/YYYY-MM-DD-slug.md`. Inclure : résumé, key claims, entités mentionnées, concepts abordés, citations marquantes, lien vers `raw/...`.
- Contradictions : `> [!warning] Contradiction` + explication.
- Incertitudes : `> [!question]`.
- Ne **jamais** modifier les fichiers dans `raw/`.

## Agents experts par domaine

L'ingestion est **déléguée à un agent expert** du domaine de la source. Les agents vivent dans `.claude/agents/` :

{{agents_section}}

Chaque agent a un prompt **volontairement ouvert** (pas une checklist fermée) et **écrit directement** dans le wiki. Il conclut par deux blocs parsables : `## Ingest summary` et `## Evolution suggestions`. Les suggestions s'accumulent dans `.claude/agents/<domain>-expert.suggestions.md`.

### Dispatch (`/ingest`)

Le main context **propose** un agent avec niveau de confiance + justification, puis l'utilisateur **valide** (ou choisit autre chose) via `AskUserQuestion`. Trois cas : confiance haute → option recommandée ; confiance faible → liste sans recommandation ; cross-domaine → multiSelect pour plusieurs experts en parallèle. Si aucun agent adapté → fallback générique dans le main context.

### Évolution des agents (`/evolve-agent <domain>`)

Consomme les `.suggestions.md` accumulées, propose un diff du prompt de l'agent, applique sur validation, archive les suggestions intégrées dans `.suggestions.archive.md`, ajoute une entrée `evolve` dans `log.md`. Boucle d'amélioration **explicite** et **curée par l'humain** — pas d'auto-modification silencieuse.

## Workflows

### INGEST (`/ingest [--force] [chemin-ou-dossier]`)

**Mode batch idempotent.** Sans argument : scanne tout `raw/`. Avec un dossier : le sous-arbre. Avec un fichier précis : force re-ingest de ce fichier. Avec `--force` (combinable) : re-ingère même les fichiers au sha256 inchangé — utile après un `/evolve-agent` pour appliquer les nouveaux réflexes aux sources déjà ingérées (mise à jour des pages existantes, pas de doublons). Le contenu effectif de l'ingest est produit par l'**agent expert** du domaine (cf. ci-dessus).

#### Détection de l'état de chaque source raw

Lancer `bash scripts/scan-raw.sh [scope]` (sans argument = tout `raw/`) pour obtenir le statut de chaque fichier :

- `NEW` — jamais couvert → ingest complet.
- `SKIP` — déjà couvert (`source_path` exact, `covered_paths`, ou répertoire parent) → ignorer (sauf `--force`).
- `MODIFIED` — couvert mais `source_sha256` changé → re-ingest.

Le script bâtit un index en mémoire à partir des champs `source_path` et `covered_paths` de toutes les pages `wiki/sources/`, ce qui évite les faux positifs « NEW » quand un agent a synthétisé plusieurs fichiers raw en une page composite.

Après scan : lister les **orphelins** (pages `wiki/sources/` dont le `source_path` n'existe plus dans `raw/`). Ne pas supprimer : flag dans le rapport pour décision manuelle.

#### Par source ingérée (nouveau ou modifié)

1. Lire (fetch si URL, ou enchaîner `scripts/transcribe.sh` si vidéo/podcast).
2. **Proposer un agent expert** (cf. section « Agents experts par domaine ») avec niveau de confiance + justification ; obtenir la validation utilisateur via `AskUserQuestion`.
3. **Spawner l'agent** avec : chemin du raw, liste des pages existantes du domaine, `wiki/domains/<d>.md`.
4. L'agent exécute l'ingest de bout en bout (écriture directe dans le wiki, frontmatter `type: source` + `source_path` (obligatoire, non-vide) + `source_sha256` + `ingested` + `domains` + `covered_paths` (obligatoire si plusieurs raw couverts), + pages `entities/` / `concepts/` / `cheatsheets/` / `diagrams/` / `syntheses/` selon ses livrables) puis renvoie son rapport.
5. Le main context :
   - Appose l'`Ingest summary` dans `log.md` (entrée `## [YYYY-MM-DD] ingest | <titre> (agent: <nom>)`).
   - Appendre les `Evolution suggestions` dans `.claude/agents/<domain>-expert.suggestions.md`.
   - Met à jour `index.md` si l'agent ne l'a pas déjà fait.
   - **Radar** : ajouter toutes les questions ouvertes remontées par l'agent dans `wiki/radar.md` (catégories : À vérifier / À rechercher / À décider / À améliorer / À surveiller). Format : `- [ ] **[Domaine · YYYY-MM-DD]** Description. → [[lien]]`. Ne pas dupliquer les entrées existantes.
   - **Cross-domain** : si le rapport contient `Cross-domain: [<domaines>]`, spawner séquentiellement l'agent expert de chaque domaine listé en lui passant : l'entité/source créée + `wiki/domains/<d>.md` + instruction explicite « mets à jour ce hub de domaine pour référencer cette entité/source ».

#### Rapport final

Format :
```
N nouveaux · M mis à jour · K inchangés (skipped) · L orphelins
```
Suivi de :
- Liste des pages créées/modifiées.
- Contradictions détectées (entre sources ou avec le wiki existant).
- Questions ouvertes ajoutées dans `wiki/radar.md`.
- Orphelins (à supprimer manuellement si volontaire).

### INGEST-VIDEO (`/ingest-video <chemin-ou-url-youtube> [--induction|--mode-a|--skip-frames|--resume]`)

Pipeline vidéo → transcript → ingest → proposition de mode d'extraction de frames → extraction → re-spawn agent pour transcription markdown.

**Mode `--resume <slug>`** : skip l'étape de transcription si `raw/transcripts/YYYY-MM-DD-<slug>.md` existe déjà (cas où la transcription a été faite en amont par un autre pipeline).

#### Conventions de stockage vidéo

- **`LLMWIKI_VIDEO_CACHE`** : variable d'environnement utilisée par `scripts/transcribe.sh`, `scripts/sample-frames.sh`, `scripts/extract-frames.sh` pour localiser les vidéos. Défaut : `cache/videos/` (disque interne, dans le vault). Override : exporte la variable vers un disque externe ou un cache dédié si tu manipules de gros volumes vidéo.
- **`cache/videos/inbox/`** : drop zone pour les vidéos non-YouTube téléchargées manuellement (extension navigateur, drag-and-drop). Tu y déposes le fichier, puis invoques le pipeline avec ce chemin.

#### Étapes 1-2 : transcript + ingest standard

1. Acquisition audio : YouTube → `yt-dlp` audio direct (pas de vidéo stockée) ; fichier local → placé dans `${LLMWIKI_VIDEO_CACHE:-cache/videos}/`, audio extrait via `ffmpeg`. Le script [scripts/transcribe.sh](scripts/transcribe.sh) couvre les deux cas.
2. Transcription locale via **whisper.cpp** ou **mlx-whisper** → `raw/transcripts/YYYY-MM-DD-<slug>.md` avec timestamps ~30s.
3. Création de `raw/videos-meta/YYYY-MM-DD-<slug>.meta.md` : URL, durée, hash, emplacement (`archived` / `deleted` / `in-cache`).
4. Purge `cache/audio/<slug>.*` après transcription.
5. Workflow INGEST standard sur le transcript (dispatch agent expert + validation utilisateur). L'agent reçoit la convention frames en contexte. Une vidéo = une source.

#### Étape 3 : choix du mode d'extraction (proposition à l'utilisateur)

Tous les agents experts disposent d'une section `## Frames visuelles` dans leur prompt — chaque agent peut donc déclarer un bloc `## Frame requests` (mode A) quel que soit le domaine.

Après l'ingest, `/ingest-video` calcule des **signaux** sur le transcript et le rapport agent :
- `duration_min` (durée vidéo)
- `visual_mentions` (count de patterns visuels dans le transcript : « regardez », « voilà », « vous voyez », « ce schéma », « ce tableau », « cette grille », « ce diagramme », « cette image », « à l'écran », etc.)
- `frame_requests_count` (entrées du bloc `## Frame requests` du rapport agent)

Puis **propose** un mode via `AskUserQuestion`, avec une recommandation justifiée :
- **Mode A — frame requests directes** : pipeline historique. Recommandé si l'agent a déclaré un nombre cohérent de frames avec la densité visuelle.
- **Mode B — induction croisée** (cf. [[decisions/extraction-frames-induction-runbook]]) : pipeline lourd en 9 étapes (sampling dense → image-diff → catalogage agent Explore → induction transcript ±30s → extraction 1080p → validation manuelle batch → promotion → re-spawn agent → transcription markdown). Recommandé pour vidéos ≥ 30 min avec densité visuelle ≥ 0.3 mention/min ET sous-extraction suspectée, ou agent qui n'a déclaré aucune frame malgré ≥ 10 mentions visuelles.
- **Skip — pas d'extraction**. Recommandé si durée < 15 min ET aucune mention visuelle.

**Override flags** sautent la proposition : `--induction` (force B), `--mode-a` (force A), `--skip-frames` (force skip).

#### Étapes 4a / 4b : exécution du mode retenu

**Mode A** : extraction one-shot via [scripts/extract-frames.sh](scripts/extract-frames.sh) → batch d'AskUserQuestion → promotion `raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png` → re-spawn agent expert (re-ingest forcé) qui transcrit chaque frame en markdown dans la page wiki concernée.

**Mode B** : pipeline complet du runbook. Scripts packagés : [scripts/sample-frames.sh](scripts/sample-frames.sh) (sampling dense, cadence paramétrable) et [scripts/diff-frames.py](scripts/diff-frames.py) (image-diff ROI optionnel — défaut plein cadre, voir Annexes domaine du runbook pour les ROI documentés). Le re-spawn de l'agent expert, en re-ingest forcé, lui demande aussi explicitement la transcription markdown de chaque frame promue.

**Cas YouTube + frame demandée sans vidéo locale** : proposer re-téléchargement du segment (`yt-dlp --download-sections "*HH:MM:SS-HH:MM:SS"`) ou annoter `> [!question] Frame non extraite — vidéo non disponible en cache`.

#### Étape 5 : sort de la vidéo locale

Pour les vidéos locales : suppression / archivage hors-vault (`~/Archive/llm-wiki-videos/`) / conservation (déconseillé). **Après** l'extraction des frames.

#### Convention frames (mode A — déclaration par l'agent)

**Format** (produit par l'agent dans son rapport, après `## Ingest summary` et `## Evolution suggestions`) :
```
## Frame requests
- FRAME: HH:MM:SS | slug-descriptif | Description précise du visuel attendu à l'écran
```

**Critères cumulatifs — les deux doivent être réunis :**
1. **Confirmation verbale explicite** : le transcript contient une phrase confirmant qu'un visuel est affiché. Une inférence ne suffit pas. Les déclencheurs verbaux propres à chaque domaine sont listés dans la section `## Frames visuelles` du prompt de chaque agent.
2. **Un visuel = une frame** : regrouper toutes les références verbales à un même visuel et ne déclarer qu'**un seul timestamp** (premier affichage complet).

**Résultat attendu** : 2-4 frames max par heure pour la plupart des cas. Certains domaines / formats de vidéos peuvent justifier des exceptions documentées (codifiées par `/evolve-agent <domain>` après quelques ingests).

#### Convention frames (mode B — pipeline runbook)

L'agent expert ne déclare pas le bloc `## Frame requests` au moment de l'ingest initial — c'est `/ingest-video` qui pilote. Voir [[decisions/extraction-frames-induction-runbook]] pour les 9 étapes du pipeline.

#### Convention nommage / référencement (modes A et B)

- **Nommage** : `raw/frames/YYYY-MM-DD-<source-slug>-<slug-descriptif>.png`
- **Référencement** : `![Label](../../../raw/frames/YYYY-MM-DD-source-slug-slug.png)`
- **Frontmatter** des pages source : `frames: [raw/frames/...]` (optionnel)
- **Transcription markdown** : chaque frame promue doit être transcrite en markdown structuré (table, Mermaid, code, liste KPIs, description sémantique, etc.) dans la page wiki qui la consomme. C'est non-optionnel — sans transcription, les `/query` doivent ré-analyser l'image à chaque appel. Le format adéquat selon le type de visuel est documenté dans la section `## Frames visuelles` du prompt de chaque agent et dans l'Étape 9 du runbook.
{{sync_repos_section}}
### SESSION START (automatique à chaque démarrage)

Vérifier les signaux dans `cache/` au démarrage :
- **`cache/.pending-ingest`** : proposer `/ingest` pour chaque chemin listé. Ne pas supprimer — attendre confirmation.
- **`cache/.session-pending`** : proposer `/compress-bb <slug>` pour archiver la session précédente. Supprimer après proposition.

Ces vérifications sont silencieuses si les fichiers sont absents.

### RADAR (« montre le radar » / « qu'est-ce qu'il y a à faire aujourd'hui »)
Quand l'utilisateur demande le radar ou la liste des choses à faire :
1. Lire `wiki/radar.md` — présenter les entrées non cochées, groupées par catégorie.
2. Lire `.claude/agents/*.suggestions.md` — extraire les suggestions récurrentes ou structurantes (≥2 apparitions, ou jugées haute valeur) et les résumer : quel agent, quel pattern, est-il mûr pour un `/evolve-agent` ?
3. Proposer une ou deux actions prioritaires pour la session.
4. Ne pas journaliser dans `log.md` (lecture seule).

### QUERY (`/query <question>`)
1. Lire `index.md` pour trouver les pages pertinentes.
2. Lire ces pages, suivre les `[[wikilinks]]` nécessaires.
3. Synthétiser avec citations `[[page]]`.
4. Si substantiel, proposer de filer dans `wiki/syntheses/<slug>.md`.
5. `log.md` : `## [YYYY-MM-DD] query | <question courte>`.

### SAVE (`/save <slug>`)
Archiver la dernière synthèse dans `wiki/syntheses/<slug>.md`, mettre à jour `index.md` et `log.md`.

### LINT (`/lint`)
- Contradictions, claims périmés, orphelines, concepts sans page, cross-refs manquantes, lacunes.
- Suggérer prochaines sources à ingérer.

### EVOLVE-AGENT (`/evolve-agent <domain>`)
Faire évoluer le prompt système de l'agent expert `<domain>-expert` à partir des suggestions qu'il a lui-même remontées lors des ingestions précédentes.
1. Lit `.claude/agents/<domain>-expert.suggestions.md` (append-only, alimenté par `/ingest`).
2. Propose un **diff** du prompt à l'utilisateur (suggestions retenues récurrentes/structurantes ; écartées l'anecdotique).
3. Sur validation : met à jour `.claude/agents/<domain>-expert.md`, archive les suggestions intégrées dans `.suggestions.archive.md`, ajoute une entrée `## [YYYY-MM-DD] evolve | <domain>-expert` dans `log.md`.
4. L'agent mis à jour sera chargé au **prochain démarrage de session** (les subagents Claude Code sont chargés au boot).

## Décisions d'architecture (`wiki/decisions/`)

Les choix structurants sur le vault lui-même (workflows, conventions, outillage — pas les domaines de connaissance) vont dans `wiki/decisions/`, pas dans `wiki/syntheses/`. Format **ADR-lite** :

- Slug descriptif, pas de numérotation.
- Frontmatter `type: decision`.
- Structure libre mais viser : **Problème** → **Options écartées** → **Décision retenue** → **Pourquoi** → **Questions ouvertes**.
- Pas de champ `status` pour l'instant. Si une décision est révisée, créer une nouvelle décision qui cite et remplace l'ancienne ; l'ancienne garde son fichier comme trace historique.

Exemples de sujets qui y vont : versioning des prompts d'agents, gestion des secrets dans le vault, conventions de snapshot pour sources évolutives, structuration des domaines.

## Principes d'écriture

- Français. Termes techniques en VO si usage.
- Une page = une idée/entité. >400 lignes → scinder. `overview.md` reste unique tant que <300 lignes, puis éclaté en sous-pages.
- Toujours citer les sources (`sources:` frontmatter + `[[source-slug]]` inline si claim précis).
- Listes et tableaux courts > paragraphes longs.
- Ton neutre pour entities/concepts, plus personnel pour overview et domains.

## Ce qu'il ne faut PAS faire

- **Règle stricte** : une source = un fichier dans `raw/`. Pas d'ingestion depuis la mémoire ou depuis la conversation. Si tu veux faire entrer un souvenir / avis / retour d'expérience, dépose-le d'abord dans `raw/notes/YYYY-MM-DD-<sujet>.md`, puis ingère normalement.
- **Ne jamais référencer `cache/` depuis le wiki.** Le contenu peut disparaître à tout moment.
- Pas de liens inventés sans justification textuelle.
- Pas de page pour chaque concept mentionné en passant — seuil : ≥2 sources OU jugé structurant par l'utilisateur.
- Pas de longues introductions.
