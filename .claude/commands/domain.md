---
description: Manage a vault domain's lifecycle (add/rename/remove) post-bootstrap
argument-hint: <add|rename|remove> <slug> [<new-slug>] [--archive|--purge] [--include-historical] [--audit-migration] [--dry-run]
---

# /domain

Gère le cycle de vie d'un domaine dans un vault BoilingBrain **après le bootstrap initial**. La commande dispatche sur le premier mot de `$ARGUMENTS` :

- `/domain add <slug>` — instancie un nouveau domaine (agent, mémoire, hub) et l'insère dans toutes les déclarations canoniques.
- `/domain rename <old-slug> <new-slug>` — renomme un domaine partout, en disambiguant les cas ambigus (slugs composés, mot en prose, aliases de wikilinks).
- `/domain remove <slug>` — supprime un domaine de l'actif du vault. `--archive` (défaut) préserve l'historique ; `--purge` propose la suppression case-by-case dans l'historique aussi.

**Hors scope** (cf. issue #38) : migration cross-domain de sources entre domaines existants, merge de domaines, split de domaines, slugs non-latins.

## Préliminaires (toujours)

Avant tout dispatch :

### 1. Vérifier le contexte

- Le cwd doit être la racine d'un vault instancié (pas le repo template). Si `CLAUDE.md.tpl` existe à la racine → STOP, expliquer à l'utilisateur que la commande ne s'exécute que dans un vault clôné.
- Le remote `template-upstream` doit être configuré (sinon le fetch des `.tpl` pour `add` échoue) :

  ```bash
  git remote get-url template-upstream 2>/dev/null || {
    git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git
    git fetch template-upstream --tags
  }
  ```

### 2. Détecter les conventions du vault

Capture dans des variables, à réutiliser plus bas :

- **`VAULT_LANGUAGE`** : `grep -oE 'Vault language[^*]*\*\*[A-Za-z]+\*\*' CLAUDE.md` puis extraire le mot ; fallback `grep 'vault_language' CLAUDE.md`. Défaut si introuvable : `English`.
- **`MEMORY_CONVENTION`** : lister `.claude/agent-memory/` et observer si les sous-dossiers ont le suffixe `-expert` ou non.
  - Si `.claude/agent-memory/<slug>-expert/` existe pour ≥1 domaine → convention `with-suffix`.
  - Si `.claude/agent-memory/<slug>/` (sans suffixe) → convention `bare`.
  - Si mixte → demander à l'utilisateur via `AskUserQuestion` quelle convention appliquer (et flagger un Radar item pour cohérence future).
- **`EXISTING_DOMAINS`** : `ls wiki/domains/*.md` filtré, excluant les hubs hors-domaine éventuels (préfixe `_`). Le slug d'un domaine = le basename sans `.md`.
- **`EXISTING_AGENTS`** : `ls .claude/agents/*-expert.md` (suffixe `-expert.md` obligatoire pour le dispatch dynamique de `/ingest`).
- **`INGEST_IS_HARDCODED`** : `grep -E '(<[a-z-]+-expert>|recommended.*<[a-z-]+>)' .claude/commands/ingest.md`. Si le grep trouve un mapping explicite → `true`. Défaut depuis bootstrap : `false` (dispatch dynamique, cf. ingest.md L48 « propose one or more expert agents from those present in .claude/agents/ »).

### 3. Dispatcher

Parse `$ARGUMENTS` :

```
<sub> <slug> [<new-slug>] [--flags...]
```

`<sub>` ∈ {`add`, `rename`, `remove`}. Si manquant ou invalide → afficher l'usage et stopper. Tout le reste passe à la sous-section correspondante.

---

## Sous-commande : `add <slug>`

### Phase 1 — Interview interactive

Bundler les questions en **un seul appel `AskUserQuestion`** (4 questions max ; les fields optionnels en suivi conditionnel).

Questions de la passe 1 (4 questions, single-select sauf indication) :

1. **Domain label** (free-form, ex. `Astrophysique`, `Mental Performance`).
2. **Deliverables signature** (multiSelect parmi : `cheatsheets`, `syntheses`, `diagrams`, `entities`, `concepts`, `cartographies`). L'issue souligne le cas multi-deliverables (ex. `cheatsheets + syntheses`).
3. **Position dans la liste `CLAUDE.md`** (single-select) : « insérer entre **<slug-i>** et **<slug-i+1>** » pour chaque paire adjacente de `EXISTING_DOMAINS`, plus l'option « en queue ». L'issue est explicite : l'insertion est conceptuelle, pas alphabétique.
4. **Audit migration ?** (`Oui` / `Non, plus tard`) — déclenche la passe `--audit-migration` après le rendu.

Passe 2 (free-form, demandée en texte libre, pas via `AskUserQuestion`) :

- `summary_l0` (≤140 chars).
- `summary_l1` (paragraphe structuré, 50-150 mots).
- `domain_intro_paragraph` (1-2 phrases en tête du hub).
- `taxonomy` (sous-thèmes initiaux, ex. liste à puces FR).
- `domain_specific_observation_section` (liste libre des angles que l'agent doit chercher dans une source du domaine — **authored dans `VAULT_LANGUAGE`**, pas traduit d'un placeholder).
- `trigger_examples` (déclencheurs visuels typiques pour les frames, ex. `tableaux de résultats, schémas d'architecture`).
- *Optionnels — laisser vide pour omettre les blocs correspondants* : `authority_table_section`, `co_ingest_section`, `confidentiality_section`, `frames_visual_formats` (override du défaut), `hub_pivot_marker` (marqueur si ce hub est le pivot du vault).

### Phase 2 — Fetch des templates upstream

```bash
git fetch template-upstream --tags
TPL_AGENT=$(git show template-upstream/main:.claude/agents/domain-expert.md.tpl)
TPL_MEMORY=$(git show template-upstream/main:.claude/agent-memory/domain-memory.md.tpl)
TPL_HUB=$(git show template-upstream/main:wiki/domains/domain.md.tpl)
```

Si l'un des `git show` échoue → STOP, expliquer que le template upstream n'est pas accessible.

### Phase 3 — Rendu

Substituer les `{{...}}` :

- `{{domain_slug}}` → `<slug>` argument.
- `{{domain_label}}` → réponse interview.
- `{{bootstrap_date}}` → date du jour `YYYY-MM-DD`.
- `{{summary_l0}}`, `{{summary_l1}}`, `{{domain_intro_paragraph}}`, `{{taxonomy_section}}`, `{{domain_specific_observation_section}}`, `{{trigger_examples}}` → réponses interview.
- `{{deliverables_signature_block}}` → générer un bloc multi-lignes listant chaque deliverable choisi avec une phrase descriptive courte (ex. `Une cheatsheet `wiki/cheatsheets/<topic>.md` par sous-thème — tableaux synthétiques, seuils, matrices.`).
- `{{authority_table_section}}`, `{{co_ingest_section}}`, `{{confidentiality_section}}`, `{{frames_visual_formats}}`, `{{hub_pivot_marker}}`, `{{related_domains_section}}` → laisser vide si l'utilisateur n'a rien donné. Si la balise apparaît seule sur une ligne → supprimer la ligne entière.
- `{{model}}` → `claude-sonnet-4-6` (défaut template) sauf si l'utilisateur précise.
- `{{maxTurns}}`, `{{effort}}` → valeurs par défaut observées dans les agents existants (`grep -h '^maxTurns:\|^effort:' .claude/agents/*-expert.md | sort -u`).
- `{{vault_language}}` → `VAULT_LANGUAGE` détecté.

Si `VAULT_LANGUAGE != English`, traduire les sections narratives du template rendu (corps du prompt, descriptions, intro du hub) tout en gardant en anglais les champs YAML techniques (`name`, `tools`, `model`, `memory`, `permissionMode`, `maxTurns`, `effort`).

### Phase 4 — Chemins de destination

Cohérents avec les conventions détectées :

| Source rendue | Destination |
|---|---|
| `TPL_AGENT` rendu | `.claude/agents/<slug>-expert.md` |
| `TPL_MEMORY` rendu | `.claude/agent-memory/<slug>(-expert)/MEMORY.md` selon `MEMORY_CONVENTION` |
| `TPL_HUB` rendu | `wiki/domains/<slug>.md` |

Créer également un fichier `.claude/agents/<slug>-expert.suggestions.md` vide (sera alimenté par `/ingest` puis consommé par `/evolve-agent`).

### Phase 5 — Insertion dans les déclarations canoniques

Pour chaque fichier, **lire** le fichier, **calculer le patch**, l'**afficher en preview**, puis appliquer après validation globale (cf. section « Validation & application »).

- **`CLAUDE.md`** :
  - Section `## User domains` : insérer une nouvelle entrée numérotée à la position choisie en Phase 1. **Incrémenter de 1 le numéro de chaque entrée située en aval de l'insertion** (regex `^(\d+)\. ` → captures + 1).
  - Section `## Per-domain expert agents` : insérer la ligne `- \`<slug>-expert\` — livrables : <résumé deliverables>. <signature one-liner>.` à la même position relative.
- **`README.md`** : si une table « Domains » ou une liste à puces existe, insérer la ligne. Sinon, log un warning « README sans table de domaines détectée, à éditer à la main ».
- **`wiki/index.md`** : section `## Domains` ou `## Domaines`, insérer la ligne `- [[domains/<slug>]] — <summary_l0>`.
- **`wiki/overview.md`** : section listant les domaines, insérer la ligne similaire.
- **`.claude/commands/ingest.md`** : si `INGEST_IS_HARDCODED == false`, **ne pas toucher** — le dispatch dynamique trouvera automatiquement `<slug>-expert.md` au prochain `/ingest`. Si `true` (vault qui a éditeé son ingest.md), localiser le mapping et ajouter une entrée ; logger un warning.

### Phase 6 — `--audit-migration` (si demandé)

Objectif : identifier les sources / concepts / entities existants qui appartiennent en réalité au nouveau domaine et devraient être re-taggés.

Pipeline en deux passes (cf. issue #38 : le filtre LLM second pass est obligatoire — sans lui, ~25/30 candidats sont des faux positifs lexicaux) :

1. **Pré-sélection lexicale** : extraire 8-12 mots-clés depuis `summary_l1` + `taxonomy_section` (mots de ≥4 chars, lowercase, hors stopwords FR/EN). `grep -ilE '(\bmot1\b|\bmot2\b|…)' wiki/sources/*.md wiki/concepts/*.md wiki/entities/*.md` → liste de candidats.
2. **Filtre LLM** : pour chaque candidat, lire son frontmatter (`summary_l1` complet) + son `domains:` actuel. Évaluer in-context (pas d'agent spawn) : « ce candidat appartient-il au domaine `<slug>` ? Donne un verdict parmi `yes`, `no`, `uncertain` avec une justification d'une ligne. ». Garder seulement les `yes` confiants pour la pré-sélection ; les `uncertain` peuvent être présentés en deuxième batch.

3. **Présentation utilisateur** : `AskUserQuestion` multiSelect, pre-checked uniquement les `yes`, listant `<path> — <verdict>: <justification>` par option (max 4 par batch, pagination via batches successifs si >4 candidats).

4. **Application** : pour chaque candidat validé, éditer `domains:` du frontmatter pour y ajouter `<slug>` (préserver les domaines existants).

### Phase 7 — Validation finale + apply

Cf. section commune « Validation & application ».

---

## Sous-commande : `rename <old-slug> <new-slug>`

### Phase 1 — Pré-validation

- Refuser si `<new-slug>` existe déjà comme domaine (`wiki/domains/<new-slug>.md` présent OU `.claude/agents/<new-slug>-expert.md` présent) → STOP, demander de choisir un autre slug ou de `remove` d'abord.
- Refuser si `<new-slug>` n'est pas en `[a-z0-9-]+` (kebab-case ASCII strict — hors scope explicite : non-latin).
- Refuser si `<old-slug>` n'existe pas dans `EXISTING_DOMAINS`.

### Phase 2 — Scan exhaustif

```bash
bash scripts/scan-domain-refs.sh <old-slug> > /tmp/scan-rename.txt
```

Bucketer la sortie en lisant chaque ligne (champ 1 = bucket).

### Phase 3 — Présentation par bucket

Présenter le **résumé global** (compteurs par bucket) avant tout, puis demander bucket par bucket. Pas de validation en bloc — chaque catégorie a son protocole propre.

#### `B1 CANONICAL` (déclarations actives)

`AskUserQuestion` Pattern D (file selection, multiSelect, **pre-checked tous**). Description par fichier : nombre d'occurrences et 1-2 lignes d'exemple. L'utilisateur peut décocher si une occurrence est suspecte.

#### `B2 FRONTMATTER` (champ `domains:`)

`AskUserQuestion` Pattern D, **pre-checked tous**. Substitution mécanique sûre — c'est de la métadonnée, pas de la prose.

#### `B3 WIKILINK` (`[[domains/<old>]]` sans alias)

`AskUserQuestion` Pattern D, **pre-checked tous**. Substitution `[[domains/<old>]]` → `[[domains/<new>]]`.

#### `B4 ALIAS` (`[[domains/<old>|Label]]`)

**Un par un**. Pour chaque alias :

```json
{
  "question": "Wikilink alias à <path>:<line> — '[[domains/<old>|<Label>]]'. Que faire ?",
  "options": [
    {"label": "Renommer slug + garder label", "description": "[[domains/<new>|<Label>]] — utile si le label est délibérément différent"},
    {"label": "Renommer slug + sync label", "description": "[[domains/<new>|<NewLabel>]] — utile si le label suivait le slug"},
    {"label": "Laisser tel quel", "description": "Skip cette occurrence"}
  ]
}
```

`<NewLabel>` est dérivé de `<new>` (Capitalize first, hyphens → spaces). L'utilisateur peut surcharger via « Other ».

#### `B5 COMPOSED` (slugs composés)

**Un par un**. Pour chaque candidat (ex. `equipe-agents-roles-<old>`) :

```json
{
  "question": "Slug composé à <path>:<line> — '<composed>'. Contient '<old>' mais semble être un identifiant à part entière. Renommer ?",
  "options": [
    {"label": "Garder tel quel", "description": "<composed> est un concept distinct (Recommandé)"},
    {"label": "Renommer", "description": "Substituer <old> → <new> dans <composed> → <new-composed>"}
  ]
}
```

Si l'utilisateur choisit « Renommer », appliquer la sub à toutes les occurrences (filename + références) du composé en question.

#### `B6 PROSE` (mot dans le corps)

**Un par un** avec une ligne de contexte. Pour chaque hit :

```json
{
  "question": "Occurrence prose à <path>:<line>. Contexte : '<line content>'. Renommer ?",
  "options": [
    {"label": "Garder tel quel", "description": "C'est un mot de la langue naturelle, pas le slug"},
    {"label": "Renommer", "description": "Substituer <old> → <new> à cette ligne"}
  ]
}
```

Pour limiter le bruit : si >30 hits PROSE, proposer un batch initial groupé « tout garder par défaut, je décoche au cas par cas ce qui doit être renommé » (Pattern D, **rien de pre-checked**).

#### `B7 LOGTAG`

Bucket sensible : ces tags structurent le log historique. Présentation `AskUserQuestion` Pattern D, **rien pre-checked**. L'utilisateur opt-in pattern par pattern. Conseil affiché : « renommer un log tag = réécrire un fait historique, généralement préférer skip ».

#### `B8 HIST` (traces historiques)

**Skip par défaut**. Si flag `--include-historical` présent, présenter par sous-bucket (log / decisions / syntheses / sources) avec `AskUserQuestion` Pattern D, **rien pre-checked**. Conseil affiché : « les pages historiques décrivent un état passé du vault. Les réécrire = falsifier l'historique. »

#### `B9 DRIFT`

**Warning final, jamais auto-fix**. Lister les hits en fin de rapport avec recommandation manuelle.

### Phase 4 — Renames physiques

Une fois toutes les validations bucket recueillies :

```bash
# Agent + suggestions
mv .claude/agents/<old>-expert.md .claude/agents/<new>-expert.md
[ -f .claude/agents/<old>-expert.suggestions.md ] && mv .claude/agents/<old>-expert.suggestions.md .claude/agents/<new>-expert.suggestions.md
[ -f .claude/agents/<old>-expert.suggestions.archive.md ] && mv .claude/agents/<old>-expert.suggestions.archive.md .claude/agents/<new>-expert.suggestions.archive.md

# Mémoire (respecter MEMORY_CONVENTION)
mv .claude/agent-memory/<old>${SUFFIX}/ .claude/agent-memory/<new>${SUFFIX}/

# Hub
mv wiki/domains/<old>.md wiki/domains/<new>.md
```

À l'intérieur de **chaque** fichier renommé, substituer toutes les références internes au slug et au label (frontmatter `name:`, `description:`, bodies, etc.).

### Phase 5 — Renumérotation `CLAUDE.md`

La rename ne touche pas la position numérique par défaut. Proposer (`AskUserQuestion`) :
- « Garder la même position numérique » (défaut).
- « Re-positionner conceptuellement » (re-poser la question Phase 1.3 de `add`).

### Phase 6 — Validation + apply

Cf. section commune.

---

## Sous-commande : `remove <slug>`

Flags : `--archive` (défaut) | `--purge` | `--include-historical` (modifie `--archive` pour proposer l'historique au cas par cas, sans déclencher le mode `--purge` global).

### Phase 1 — Pré-validation

- Refuser si `<slug>` est le **seul domaine** du vault (`|EXISTING_DOMAINS| == 1`) → l'écosystème ne fonctionne pas sans au moins un domaine. Cf. `BOOTSTRAP.md`.
- Refuser si `<slug>` n'existe pas dans `EXISTING_DOMAINS`.

### Phase 2 — Scan

```bash
bash scripts/scan-domain-refs.sh <slug> > /tmp/scan-remove.txt
```

### Phase 3 — Présentation par bucket

Mode `--archive` (défaut) : strip uniquement B1-B4. B5/B6/B7 par défaut skip (warnings). B8 préservé. B9 warning.

Mode `--purge` : strip B1-B4 **plus** propose B5/B6/B7/B8 case-by-case (mêmes protocoles que `rename`, mais l'action est suppression de l'occurrence au lieu de substitution).

#### B1 CANONICAL (active)

`AskUserQuestion` Pattern D, **pre-checked tous**. Suppression de la ligne (ou de l'entrée numérotée) correspondant au slug.

#### B2 FRONTMATTER

`AskUserQuestion` Pattern D, **pre-checked tous**. Pour `domains: [a, <slug>, b]` → retirer `<slug>` ; si `domains` devient vide, **ne pas supprimer la page** (warning : page sans domaine), demander à l'utilisateur si la page doit être re-taggée vers un autre domaine ou laissée orpheline.

#### B3 WIKILINK / B4 ALIAS

`AskUserQuestion` Pattern D, **pre-checked tous**. Suppression de la ligne hôte (les wikilinks `[[domains/<slug>]]` n'ont plus de cible une fois `wiki/domains/<slug>.md` supprimé). Si la ligne contient d'autres contenus utiles → demander à l'utilisateur (split de la ligne ou conservation).

#### B5/B6/B7

`--archive` : skip silencieux, listés en warnings finaux.
`--purge` : proposés case-by-case (« supprimer la ligne ? remplacer par texte vide ? »).

#### B8 HIST

`--archive` : préservé (par défaut).
`--include-historical` : proposé par sous-bucket avec `AskUserQuestion` Pattern D, **rien pre-checked**.
`--purge` : impliquant `--include-historical`, propose B8 et les autres.

### Phase 4 — Suppressions physiques

```bash
rm .claude/agents/<slug>-expert.md
rm -f .claude/agents/<slug>-expert.suggestions.md
rm -f .claude/agents/<slug>-expert.suggestions.archive.md
rm -rf .claude/agent-memory/<slug>${SUFFIX}/
rm wiki/domains/<slug>.md
```

### Phase 5 — Renumérotation `CLAUDE.md`

Renuméroter les entrées en aval de la position supprimée dans `## User domains`. Idem pour toute autre liste numérotée.

### Phase 6 — Validation + apply

Cf. section commune.

---

## Validation & application (commune aux 3 sous-commandes)

### A. Phase de scan (read-only)

Toute la commande commence par produire un **plan de changements** sans rien modifier. Les étapes 1-3 de chaque sous-commande sont en lecture pure.

### B. Phase de preview

Afficher à l'utilisateur :

- **Résumé global** : « Vault: <path>. Sous-commande: <sub>. Slug(s): <slugs>. Buckets impactés : B1:<N1>, B2:<N2>, … ».
- **Liste des renames physiques** (fichiers + dossiers).
- **Liste des fichiers modifiés** (groupée par bucket).
- **Warnings** : B9 DRIFT, B5/B6/B7 skippés (en `--archive`), incohérences inter-bucket si détectées.

### C. Phase de validation finale

`AskUserQuestion` :

```json
{
  "question": "Appliquer les changements ?",
  "header": "Apply ?",
  "options": [
    {"label": "Apply", "description": "Exécuter renames + edits + suppressions"},
    {"label": "Apply (dry-run)", "description": "Lister les commandes shell sans les exécuter (debug)"},
    {"label": "Abort", "description": "Ne rien faire, conserver le plan en /tmp"}
  ]
}
```

### D. Phase d'application

Ordre strict (les renames physiques d'abord pour éviter d'éditer des fichiers qui vont disparaître) :

1. Renames physiques (`mv`).
2. Suppressions physiques (`rm`).
3. Edits de contenu (substitutions, suppressions de lignes, renumérotations).
4. Création de fichiers (rendu des templates pour `add`).

Si une étape échoue à mi-chemin :
- Logger l'erreur, **ne pas continuer**.
- Suggérer à l'utilisateur de checkpointer Git (`git status` + commit/stash) avant de re-tenter.
- Le plan est en `/tmp/domain-plan-<timestamp>.txt` pour debug.

### E. Phase de journalisation

Append à `wiki/log.md` :

```
## [YYYY-MM-DD] domain | <sub> <slug>[<→ new-slug>]

<N> fichiers touchés. Buckets : <B1:N1, B2:N2, …>. Warnings : <B9 hits si présent, B5/B6/B7 skippés si --archive>.
```

### F. Rapport final

- Compteurs par bucket (touched / skipped).
- Liste des warnings non traités (drift numérique, slugs composés skipés, etc.).
- Prochaine étape suggérée :
  - Après `add` : `/ingest raw/<recent-folder>/` pour tester le nouvel agent sur une source.
  - Après `rename` : `/lint` pour vérifier qu'aucun wikilink ne pointe sur l'ancien slug.
  - Après `remove` : `/lint` pour détecter les orphelins.

---

## Principes

- **L'historique est sacré** : par défaut, `wiki/log.md`, `wiki/decisions/*`, `wiki/syntheses/*`, `wiki/sources/*` ne sont jamais réécrits. Opt-in explicite via `--include-historical` ou `--purge`.
- **Ambiguïté → humain** : tout cas où une heuristique pourrait se tromper (composés, prose, aliases) est présenté individuellement à l'utilisateur. Aucune réécriture silencieuse.
- **Idempotence** : re-lancer la commande sur un domaine déjà ajouté/renommé/supprimé doit produire un plan vide ou minimal (et le préciser).
- **Pas de touche au dispatch dynamique** : `/ingest` charge ses agents en lisant `.claude/agents/` — l'ajout/suppression du fichier `<slug>-expert.md` suffit. Ne pas éditer `.claude/commands/ingest.md` sauf si un mapping hardcodé est détecté.
