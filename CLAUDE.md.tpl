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
  commands/      # slash commands (/ingest, /ingest-video, /query, /save, /lint, /evolve-agent, /update-vault, /create-issue{{slash_commands_extras}})
  rules/         # conventions auto-chargées par Claude Code via le champ `paths` du frontmatter
  template-version  # version du template avec laquelle ce vault est aligné

raw/                 # sources brutes IMMUTABLES — ce qui est référencé par le wiki.
  notes/             # retours d'expérience perso (texte)
  transcripts/       # transcripts de vidéos/audios (YYYY-MM-DD-slug.md + timestamps)
  videos-meta/       # pointeurs/metadata des vidéos
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
  radar.md     # questions ouvertes & points d'attention — alimenté à chaque ingest
  overview.md  # portrait de l'utilisateur, mis à jour au fil de l'eau
  domains/     # pages racines des grands domaines (hubs)
  entities/    # personnes, entreprises, produits, lieux
  concepts/    # idées, théories, frameworks
  sources/     # une page par source ingérée (YYYY-MM-DD-slug.md)
  syntheses/   # réponses substantielles archivées
  decisions/   # choix d'architecture du vault lui-même (ADR-lite)
  cheatsheets/ # tableaux synthétiques, paliers, matrices
  diagrams/    # diagrammes Mermaid / ASCII

scripts/       # utilitaires (extraction audio, transcription, sampling de frames, image-diff{{tracked_repos_scripts_extras}})
  migrations/  # migrations breaking entre versions du template, invoquées par /update-vault
```

## Domaines de l'utilisateur

{{domains_section}}

Chaque domaine a une page dans `wiki/domains/` qui sert de hub.

## Conventions

Les conventions d'écriture (frontmatter, slugs, callouts, immutabilité de `raw/`) sont formalisées dans `.claude/rules/` et **auto-chargées** par Claude Code via le champ `paths` du frontmatter de chaque rule. Voir `.claude/rules/frontmatter.md`, `.claude/rules/pages-wiki.md`, `.claude/rules/raw-vs-cache.md`.

Trois règles critiques résiduelles :

- **`raw/` est strictement immutable.** Aucune exception. Aucun agent ni script ne réécrit un fichier de `raw/`.
- **Frontmatter YAML obligatoire** sur chaque page wiki, avec `source_sha256` calculé via `shasum -a 256 <file>` — jamais un placeholder textuel.
- **Slugs en `kebab-case.md`**, liens internes en `[[wikilinks]]` style Obsidian.

## Agents experts par domaine

L'ingestion est **déléguée à un agent expert** du domaine de la source. Les agents vivent dans `.claude/agents/` :

{{agents_section}}

Chaque agent a un prompt **volontairement ouvert** (pas une checklist fermée) et **écrit directement** dans le wiki. Il conclut par deux blocs parsables : `## Ingest summary` et `## Evolution suggestions`. Les suggestions s'accumulent dans `.claude/agents/<domain>-expert.suggestions.md` pour alimenter `/evolve-agent`.

Le dispatch d'agent à `/ingest` propose un agent avec niveau de confiance + justification, puis l'utilisateur valide via `AskUserQuestion`. Voir `.claude/commands/ingest.md` pour le détail.

## Workflows

Les workflows détaillés vivent dans `.claude/commands/`. Tableau récapitulatif :

| Slash-command | Rôle |
|---|---|
| `/ingest [chemin]` | Ingestion idempotente des `raw/` via agent expert du domaine |
| `/ingest-video <url-ou-path>` | Pipeline vidéo → transcript → ingest → frames (optionnel) |
| `/sync-repos [noms]` | Snapshot immuable des repos GitHub trackés (si `tracked-repos.config.json` présent) |
| `/query <question>` | Recherche dans le wiki avec citations, archive optionnelle |
| `/save <slug>` | Archive la dernière synthèse dans `wiki/syntheses/` |
| `/lint` | Détection de contradictions, orphelins, lacunes |
| `/evolve-agent <domain>` | Évolution curée du prompt d'un agent depuis ses suggestions accumulées |
| `/update-vault` | Récupère les améliorations upstream du template (machine de migration versionnée) |
| `/create-issue [type]` | Crée une issue sanitizée sur le repo template upstream à partir du contexte courant |
| `/compress-bb [slug]` | Sauvegarde le journal de la session courante dans `raw/notes/sessions/YYYY-MM-DD-<slug>.md` |

Pour le radar : « montre le radar » / « qu'est-ce qu'il y a à faire aujourd'hui » → lecture de `wiki/radar.md` + extraction des suggestions accumulées des agents (≥2 occurrences ou jugées structurantes). **Si une entrée du radar concerne l'environnement template** (bug ou manque touchant `scripts/`, `.claude/commands/`, `BOOTSTRAP.md`, ou tout fichier propagé par `/update-vault`), proposer à l'utilisateur de la remonter via `/create-issue <type>` — sans créer l'issue tout seul, juste suggérer la commande.

## Décisions d'architecture

Les choix structurants sur le vault (workflows, conventions, outillage — pas les domaines de connaissance) vont dans `wiki/decisions/` au format ADR-lite : Problème → Options écartées → Décision retenue → Pourquoi → Questions ouvertes. Pas de numérotation, slug descriptif. Si une décision est révisée, créer une nouvelle qui cite et remplace l'ancienne.

## Démarrage de session (signaux `cache/`)

Au démarrage de chaque session, vérifier les signaux laissés dans `cache/` :

- **`cache/.pending-ingest`** : un ou plusieurs chemins en attente d'ingestion (déposés via le MCP `drop_to_raw` ou par un autre vault). Proposer `/ingest <chemin>` pour chaque entrée. Ne pas supprimer le fichier — attendre la confirmation utilisateur.
- **`cache/.session-pending`** : la session précédente avait des changements non journalisés (commits + fichiers modifiés détectés par le hook `Stop`). Proposer `/compress-bb <slug>` pour archiver le journal dans `raw/notes/sessions/`. Supprimer le fichier après proposition.

Ces vérifications sont silencieuses si les fichiers sont absents.

## Principes d'écriture

- Français. Termes techniques en VO si l'usage VO est dominant.
- Une page = une idée/entité. >400 lignes → scinder.
- Toujours citer les sources (`sources:` frontmatter + `[[source-slug]]` inline si claim précis).
- Listes et tableaux courts > paragraphes longs.
- Ton neutre pour `entities/`, `concepts/`. Plus personnel pour `overview` et `domains/`.

## Ce qu'il ne faut PAS faire

- **Une source = un fichier dans `raw/`.** Pas d'ingestion depuis la mémoire ou la conversation. Pour faire entrer un retour d'expérience : déposer d'abord dans `raw/notes/YYYY-MM-DD-<sujet>.md`, puis ingest normal.
- **Ne jamais référencer `cache/` depuis le wiki.** Le contenu peut disparaître à tout moment.
- **Ne jamais modifier les fichiers dans `raw/`.** Une source qui évolue → nouveau fichier, jamais réécriture.
- **Pas de page pour chaque concept mentionné en passant** : seuil ≥ 2 sources OU jugé structurant par l'utilisateur.
- **Pas de longues introductions, pas de méta-commentaires.**
