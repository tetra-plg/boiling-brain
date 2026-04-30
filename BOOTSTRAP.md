# BOOTSTRAP.md — prompt portable de personnalisation du LLM Wiki

> Tu (Claude) lis ce fichier dans un clone fraîchement récupéré de `tetra-plg/llm-wiki-template`. Ta mission : conduire l'utilisateur en interview, déduire son architecture, scaffolder son instance LLM Wiki personnalisée, puis nettoyer.
>
> Tout au long du prompt, langue d'interaction = **français**. Sois direct, pas de prose. Les `AskUserQuestion` doivent être posés tels que spécifiés.

---

## Section 1 — Préambule (à internaliser)

### 1.1 Ce qu'est un LLM Wiki

Un **LLM Wiki** est un wiki personnel maintenu par LLM :

- L'humain dépose des sources brutes (notes, transcripts vidéo, PDFs, clippings, docs officielles, snapshots de repos) dans `raw/` — **immutable**.
- Des **agents experts par domaine** (un par domaine déclaré) ingèrent ces sources, écrivent dans `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, et leur livrable signature (`cheatsheets/`, `syntheses/`, `diagrams/`).
- Des **slash-commands** orchestrent : `/ingest`, `/query`, `/save`, `/lint`, `/evolve-agent`, et conditionnellement `/ingest-video`, `/sync-repos`.
- Le wiki est **toujours dérivable** de `raw/`. Pas de connaissance orpheline. Pas de lien inventé.

### 1.2 Rôles

- **Humain** : curate les sources, pose les questions, valide les arbitrages.
- **LLM (toi pendant le bootstrap, puis les agents experts ensuite)** : lit, synthétise, cross-référence, maintient. Ne jamais inventer hors source.

### 1.3 Principes structurants (les graver pendant le bootstrap)

- `raw/` = jamais modifié, jamais réécrit, hash-addressé (`source_sha256`).
- `cache/` = transitoire, jamais référencé par le wiki.
- Liens internes en `[[wikilinks]]` Obsidian, pages en kebab-case, frontmatter YAML obligatoire.
- Tiered loading : chaque page porte `summary_l0` (≤140 chars) + `summary_l1` (2-5 phrases). Permet aux agents de scanner un domaine sans charger les bodies.
- Pas d'ingestion depuis la mémoire ou la conversation : une source = un fichier dans `raw/`.

### 1.4 Ce que tu vas faire (vue d'ensemble)

1. Interview en 7 questions (Section 2).
2. Déduction des 5 propriétés par domaine (Section 3).
3. Validation par domaine + global (Section 4).
4. Génération : substitution placeholders, duplication par domaine, suppressions conditionnelles, déplacement de ce fichier en ADR, reset git (Section 5).
5. Remote GitHub optionnel (Section 6).
6. Récap onboarding + 3 prochaines actions (Section 7).

---

## Section 2 — Étape 1, Interview (7 questions)

Pose les questions **séquentiellement**. Stocke chaque réponse dans une variable interne. **Ne passe à la suivante que quand la précédente est résolue.**

### Q1 — Identité

Pose 2 questions en texte simple, séquentielles, pas via `AskUserQuestion` :

1. « Quel est ton nom complet ? (ex. *Pierre Le Guern*, *Maria Dupont*) »
   → Stocke comme `name`. Extrais le **prénom** (1er token avant l'espace) lowercased pour calculer `vault_name = <prenom>-vault`.
   → Pour les prénoms composés avec tiret (« Jean-Marc »), splitte sur **espaces uniquement** : `vault_name = jean-marc-vault`.

2. « Quel est ton rôle pro court (1 ligne) ? (ex. *VP Engineering chez Merim*, *Chercheure post-doc en génomique au CNRS*) »
   → Stocke comme `role`.

**Parsing :**
- `name` = réponse Q1.1 brute (ex. `"Maria Dupont"`).
- `role` = réponse Q1.2 brute.
- `vault_name` = `<premier_token_lowercase>-vault`. Le « premier token » est obtenu par split sur **espaces uniquement** (pas sur tirets). Donc `"Maria Dupont"` → `maria-vault`, `"Jean-Marc Lefebvre"` → `jean-marc-vault`. Confirme silencieusement, pas de question dédiée.

### Q2 — Domaines de connaissance

Pose en free-text simple (pas d'`AskUserQuestion` — la liste est ouverte) :

```
Liste les domaines de connaissance que tu veux maintenir.
Format: slugs en kebab-case, séparés par des virgules.
Exemple Pierre: poker, ia, factory, metier, tech, astro
Conseil: regroupe plutôt que d'éclater quand c'est naturel. Pas de plafond — déclare autant de domaines que pertinent.
```

**Parsing :**
- `domains = [slugs...]`. Trim chaque slug. Vérifie kebab-case, corrige sinon (silencieux).
- Si 0 domaine → re-pose la question en disant qu'il en faut au moins 1.
- Pour chaque slug, déduis un `domain_label` par titre-cassing humain (ex. `astro-physics` → `Astronomie & Physique`, `ia` → `IA`). Présenteras au moment de la validation.

**Mapping slug → label humain (titre du domaine)** :
- Slug en kebab-case ASCII (ex. `marche`, `paleo-dna`).
- Le label humain est dérivé pour affichage : capitalize + accents si pertinent (ex. `marche` → `Marché`, `paleo-dna` → `Paleo-DNA`).
- En cas d'ambiguïté (ex. slug `cs` → `Computer Science` ou `Customer Success` ?), demande à l'utilisateur de confirmer le label humain.

### Q3 — Hub pivot

Single-select dynamique avec une option par domaine + « aucun ». **Avant de poser la question**, affiche cette consigne courte en texte :

> « Si tu hésites, choisis « aucun » — tu pourras désigner un hub plus tard via `/evolve-agent`. »

Construis le JSON dynamiquement :

```json
{
  "questions": [{
    "question": "Quel domaine joue le rôle de hub pivot (irrigue les autres) ?",
    "header": "Hub pivot",
    "multiSelect": false,
    "options": [
      {"label": "<domain_slug_1>", "description": "<domain_slug_1> outille / alimente les autres domaines."},
      {"label": "<domain_slug_2>", "description": "<domain_slug_2> outille / alimente les autres domaines."},
      ...
      {"label": "aucun", "description": "Mes domaines sont indépendants. Je désignerai un hub plus tard si besoin via /evolve-agent."}
    ]
  }]
}
```

**Exemple concret** pour `domains = [poker, ia, factory, metier, tech]` : 5 options labellisées `poker`/`ia`/.../`tech` + l'option `aucun`. Description statique : « Le hub pivot est le domaine qui outille ou alimente les autres. Ex: l'IA alimente la Factory (agents) et le Métier (techniques LLM). »

**Parsing :**
- `hub_pivot = <slug>` ou `null` si « aucun ».

### Q4 — Projets en cours

Free-text :

```
2 à 3 projets actifs en ce moment, un par ligne, format:
slug | description en 1 phrase

Exemple:
kill-tilt-masterclass | suivre la masterclass poker MTT 2026
factory-v6 | refonte du plugin Factory en architecture multi-agents
```

**Parsing :**
- `projects = [{slug, description}, ...]`. Liste vide acceptée (utiliseras `« (à compléter) »` plus tard).

**Parsing tolérant** :
- Si la ligne contient `|` → split sur le premier `|` uniquement (slug à gauche, description à droite).
- Si pas de `|` mais ligne ressemble à un slug suivi d'espaces et texte → essaie de splitter sur le 1er espace après le slug (slug = continu sans espace).
- Si ambigu → re-pose la question avec exemple explicite.

### Q5 — Types de sources

Multi-select 6 options :

```json
{
  "questions": [{
    "question": "Quels types de sources comptes-tu ingérer ?",
    "header": "Types de sources",
    "multiSelect": true,
    "options": [
      {"label": "Notes perso", "description": "Réflexions, retours d'expérience, drafts personnels."},
      {"label": "Transcripts vidéo", "description": "YouTube + fichiers locaux. Active /ingest-video et le pipeline frames."},
      {"label": "PDFs", "description": "Papers, ebooks, slides."},
      {"label": "Clippings web", "description": "Articles de blog, threads, posts."},
      {"label": "Docs officielles", "description": "SDK, API, frameworks."},
      {"label": "Repos GitHub", "description": "Suivi de projets en évolution. Active /sync-repos."}
    ]
  }]
}
```

**Parsing :**
- `source_types = [labels...]`.
- `ingest_video_enabled = "Transcripts vidéo" in source_types` (booléen).
- `has_tracked_repos = "Repos GitHub" in source_types` (booléen).

### Q6 — Cadence d'ingestion

Single-select 3 options :

```json
{
  "questions": [{
    "question": "À quelle cadence comptes-tu ingérer ?",
    "header": "Cadence",
    "multiSelect": false,
    "options": [
      {"label": "< 1 par semaine", "description": "Faible volume. Favorise le coût (haiku/medium par défaut)."},
      {"label": "1 à 3 par semaine", "description": "Cadence standard."},
      {"label": "> 3 par semaine", "description": "Volume élevé. Favorise la qualité (sonnet/high par défaut sur agents non-pivot denses)."}
    ]
  }]
}
```

**Parsing :**
- `cadence ∈ {"low", "medium", "high"}`.

### Q7 — Storage vidéo (conditionnel)

Pose **uniquement si** `ingest_video_enabled = true`. Free-text :

```
Chemin du cache vidéo (où seront stockées les vidéos avant transcription).
Défaut: cache/videos/ (interne au vault, sur ton disque principal).
Si tu as un SSD externe pour les vidéos lourdes : indique son chemin (ex. /Volumes/T7/llm-wiki-cache/videos/).
```

**Parsing :**
- `video_cache_path` = réponse, défaut `cache/videos/` si vide.

---

## Section 3 — Étape 2, Déduction (B1-B5 par domaine)

Pour chaque `domain_slug` dans `domains`, déduis 5 propriétés. **Tu fais ce travail toi-même, pas l'utilisateur.** Il validera ensuite.

### B1 — `trigger_examples` (4-6 phrases verbales)

Phrases qu'on entendrait dans un transcript vidéo de ce domaine et qui signaleraient qu'un visuel est à l'écran. Déduis du label.

Patterns calibrants :
- **Données / chiffres / matrices** (poker, finance, sport stats) → « regardez le tableau », « voilà la grille », « vous les voyez », « cette colonne », « cette case ».
- **Schémas / architectures / flux** (ia, devops, factory, tech) → « ce schéma », « voilà l'architecture », « ce diagramme », « cette flèche », « ce composant ».
- **Formules / équations** (physique, math, astro) → « cette formule », « voilà l'équation », « cette démonstration », « ce calcul ».
- **Interfaces / outils / captures** (devtool, UX) → « regardez l'écran », « voilà la capture », « ce bouton », « cette interface ».
- **Réflexif / management / qualitatif** (metier, leadership, philo) → 0-3 phrases seulement, ex. « ce framework », « cette grille de lecture », « voilà la matrice ».

**Exemple concret pour `data-science`** : `["regardez le tableau", "ce graphique", "cette courbe", "voilà la matrice de confusion", "vous voyez l'histogramme"]`.

### B2 — `deliverables` (livrable signature)

Heuristique :
- Domaine **technique-dense** (chiffres, ranges, taux, KPIs) → `[cheatsheets]`.
- Domaine **réflexif** (patterns, frameworks, retours d'expérience) → `[syntheses]`.
- Domaine **système** (architectures, flux, composants) → `[diagrams]`.
- Domaine **mixte** → `[cheatsheets, syntheses]`. Typique pour `ia` (chiffres ET patterns).

Ajoute toujours implicitement les livrables de base : `[sources, entities, concepts]` (universels).

### B3 — `co_ingest_partners`

- Si `hub_pivot != null` ET `domain_slug != hub_pivot` → `co_ingest_partners = [hub_pivot]`.
- Si `domain_slug == hub_pivot` ou `hub_pivot == null` → `co_ingest_partners = []`.

### B4 — `model` / `effort` / `maxTurns`

Table de décision :

| Condition | model | effort | maxTurns |
|---|---|---|---|
| `is_hub_pivot = true` | `sonnet` | `high` | `80` |
| Domaine technique-dense (B2 contient `cheatsheets`) | `sonnet` | `high` | `60` |
| `cadence = "high"` ET pas réflexif pur | `sonnet` | `high` | `60` |
| Sinon (default) | `haiku` | `medium` | `60` |

**Priorité en cas de conflit** :
1. `is_hub_pivot = true` → toujours `sonnet/high/80`.
2. Sinon, `deliverables` contient `cheatsheets` → `sonnet/high/60` (densité technique justifie le coût même en cadence basse).
3. Sinon, `cadence = high (>3/sem)` → `sonnet/high/60` (volume justifie qualité).
4. Default → `haiku/medium/60`.

### B5 — `is_hub_pivot`

Trivial : `is_hub_pivot = (domain_slug == hub_pivot)`.

### B6 — frames_visual_formats (4-6 formats de transcription markdown)

Pour chaque domaine, déduis 4-6 formats utiles pour transcrire les frames vidéo en markdown structuré.

Patterns par type de domaine :
- **Données / chiffres / matrices** (poker, finance, sport stats) : « tableau Markdown », « table avec colonnes profondeur × position », « grille 13×13 », « palmarès chiffré ».
- **Schémas / architectures / flux** (ia, factory, devops) : « diagramme Mermaid », « flowchart », « graph LR », « sequenceDiagram ».
- **Formules / équations / démonstrations** (physique, math, biostat) : « bloc LaTeX », « équation inline », « table de variables », « démonstration pas-à-pas ».
- **Interfaces / outils / captures** (devtool, UX) : « description d'UI », « table de raccourcis clavier », « bullet de boutons cliqués ».
- **Réflexif / management / qualitatif** (metier, leadership) : « table 2D framework × axes », « bullet list de patterns », « citation marquante encadrée ».

L'utilisateur peut éditer en validation domaine.

### Autres déductions accessoires

- `summary_l0` (≤140 chars) : génère un draft à partir du label + livrable. Ex. `"Hub IA — agents, LLM, orchestration. Outille la Factory et alimente les techniques de management LLM."`.
- `summary_l1` (2-5 phrases) : draft pareil, plus détaillé.
- `domain_intro_paragraph` : 2-3 lignes en H1 du hub.
- `parcours_short` : draft 2-4 bullets à partir de Q1 `role` + Q4 `projects`. À éditer ensuite par l'utilisateur.
- `taxonomy_section` : laisse vide initialement (`(à étoffer au fil des ingests)`) — l'utilisateur n'a pas envie d'inventer une taxonomie à froid.
- `authority_table_enabled` : `true` pour domaines réflexifs où l'autorité de la source compte (ia, science, métier d'analyse) ; `false` sinon. Tu peux te baser sur le label.
- `confidentiality_block` : non-vide uniquement pour `metier` ou tout domaine que l'utilisateur a explicitement marqué sensible (à demander pendant la validation si doute).
- `bootstrap_date` : `date +%Y-%m-%d` shell.

---

## Section 4 — Étape 3, Validation (par domaine + global)

### 4.1 Validation par domaine

**Pour chaque** `domain_slug` (boucle), affiche un bloc récap markdown puis pose un `AskUserQuestion` :

```markdown
### Domaine : {{domain_label}} (`{{domain_slug}}`)

- **Hub pivot** : {{ "oui ⭐" if is_hub_pivot else "non" }}
- **Livrable signature** : {{ deliverables joined }} — {{ justification 1 ligne }}
- **Trigger phrases** (visuels dans transcripts vidéo) :
  - « {{ trigger_1 }} »
  - « {{ trigger_2 }} »
  - …
- **Co-ingest partners** : {{ co_ingest_partners or "[] (aucun)" }}
- **Model** : {{ model }} · **Effort** : {{ effort }} · **MaxTurns** : {{ maxTurns }}
```

Puis :

```json
{
  "questions": [{
    "question": "Domaine {{domain_slug}} — valides-tu cette config ?",
    "header": "Validation domaine",
    "multiSelect": false,
    "options": [
      {"label": "✅ Valide ce domaine", "description": "Garde la déduction telle quelle."},
      {"label": "✏️ Ajuste", "description": "Édite une ou plusieurs des 5 propriétés (triggers, livrables, co-ingest, model/effort/maxTurns, hub pivot)."}
    ]
  }]
}
```

Sur « ✏️ Ajuste » :

1. Affiche un `AskUserQuestion` **multiSelect** : « Quelles propriétés veux-tu éditer ? » avec 5 options (B1 trigger_examples, B2 deliverables, B3 co_ingest_partners, B4 model/effort/maxTurns, B5 frames_visual_formats).
2. Pour chaque propriété cochée seulement, prompt texte ciblé avec la valeur courante affichée et demande la nouvelle.
3. Re-affiche le bloc récap édité, redemande validation.

### 4.2 Validation globale

Une fois tous les domaines validés individuellement, affiche un récap complet :

```markdown
## Récap final

**Identité** : {{name}} — {{role}}
**Vault** : `{{vault_name}}`
**Cadence** : {{cadence}}
**Types de sources** : {{source_types joined}}
{{ "**Storage vidéo** : " + video_cache_path if ingest_video_enabled else "" }}

**Projets en cours** :
- {{ project_1.slug }} | {{ project_1.description }}
- ...

**Domaines** ({{N}}) :
- {{ domain_1_slug }} {{ "⭐" if pivot }} — {{ deliverables }} — {{ model }}/{{ effort }}/{{ maxTurns }}
- ...
```

Puis :

```json
{
  "questions": [{
    "question": "Tout est bon ?",
    "header": "Validation finale",
    "multiSelect": false,
    "options": [
      {"label": "✅ Tout est bon, scaffolde", "description": "Lance la génération du vault."},
      {"label": "↩️ Refais l'interview depuis le début", "description": "Reprend Q1. Toutes les réponses sont effacées."}
    ]
  }]
}
```

Si « ↩️ » → repars de Q1. Sinon → Section 5.

---

## Section 5 — Étape 4, Génération du vault

Exécute dans **cet ordre exact**. Utilise `Edit replace_all=true` ou `sed` pour les substitutions, `Bash` pour les `mv`/`rm`/`cp`/`git`.

### 5.1 Substitution des 28 placeholders (référence : `PLACEHOLDERS.md` à la racine)

Pour chaque fichier `.tpl` du repo (CLAUDE.md.tpl, wiki/index.md.tpl, wiki/log.md.tpl, wiki/overview.md.tpl, wiki/radar.md.tpl, wiki/domains/domain.md.tpl, .claude/agents/domain-expert.md.tpl, .claude/agent-memory/domain-memory.md.tpl) :

- Charge le contenu.
- Substitue tous les placeholders **globaux** : `{{name}}`, `{{vault_name}}`, `{{role}}`, `{{parcours_short}}`, `{{bootstrap_date}}`, `{{has_tracked_repos}}` (et ses sections conditionnelles : `{{slash_commands_extras}}`, `{{tracked_repos_arborescence}}`, `{{tracked_repos_cache}}`, `{{tracked_repos_scripts_extras}}`, `{{sync_repos_section}}`).
- Substitue les placeholders **cross-domain** calculés : `{{domains_section}}`, `{{domains_index_section}}`, `{{domains_links}}`, `{{projects_links}}`, `{{agents_section}}`.

**Note** : `tracked-repos.config.json.tpl` ne contient aucun placeholder, skipper la substitution. Le renommage final sera géré en Section 5.6.

> Pour `{{has_tracked_repos}} = false`, les 5 placeholders conditionnels deviennent des chaînes vides (cf. table dans `PLACEHOLDERS.md`).
> Pour `{{has_tracked_repos}} = true`, copie le bloc complet `### SYNC-REPOS` fourni en **Annexe D** ci-dessous (verbatim, à la place du placeholder `{{sync_repos_section}}`).

### 5.2 Duplication par domaine — agents

Pour chaque `domain_slug` dans `domains` :

```bash
cp .claude/agents/domain-expert.md.tpl .claude/agents/{{domain_slug}}-expert.md
```

Puis substitue dans la copie les **17 placeholders per-domain** : `{{domain_slug}}`, `{{domain_label}}`, `{{is_hub_pivot}}`, `{{hub_pivot_marker}}`, `{{summary_l0}}`, `{{summary_l1}}`, `{{domain_intro_paragraph}}`, `{{taxonomy_section}}`, `{{related_domains_section}}`, `{{deliverables}}`, `{{deliverables_signature_block}}`, `{{trigger_examples}}`, `{{frames_visual_formats}}`, `{{co_ingest_partners}}`, `{{co_ingest_section}}`, `{{authority_table_enabled}}`, `{{authority_table_section}}`, `{{confidentiality_block}}`, `{{confidentiality_section}}`, `{{domain_specific_observation_section}}`, `{{model}}`, `{{effort}}`, `{{maxTurns}}`.

### 5.3 Duplication par domaine — hubs

Pour chaque `domain_slug` :

```bash
cp wiki/domains/domain.md.tpl wiki/domains/{{domain_slug}}.md
```

Substitue les placeholders per-domain (mêmes valeurs que 5.2 sauf qu'on ne ré-écrit pas tout — voir mapping dans PLACEHOLDERS.md).

### 5.4 Duplication par domaine — mémoires agents

Pour chaque `domain_slug` :

```bash
mkdir -p .claude/agent-memory/{{domain_slug}}
cp .claude/agent-memory/domain-memory.md.tpl .claude/agent-memory/{{domain_slug}}/MEMORY.md
```

Substitue.

### 5.5 Suppressions conditionnelles

**Si `ingest_video_enabled = false`** :

```bash
rm .claude/commands/ingest-video.md
rm scripts/transcribe.sh scripts/sample-frames.sh scripts/extract-frames.sh scripts/diff-frames.py
rm wiki/decisions/extraction-frames-induction-runbook.md
rm wiki/decisions/ingest-video-modes-a-b-generalisation.md
```

**Si `has_tracked_repos = false`** :

```bash
rm .claude/commands/sync-repos.md
rm scripts/sync-repos.sh
rm tracked-repos.config.json.tpl    # ou son rendu si déjà substitué
rm wiki/decisions/tracked-repos-immutable-snapshots.md
```

### 5.6 Renommage des `.tpl` substitués vers leur nom final

Une fois la substitution faite, renomme les templates **uniques** (pas ceux dupliqués par domaine, déjà renommés) :

```bash
mv CLAUDE.md.tpl CLAUDE.md
mv wiki/index.md.tpl wiki/index.md
mv wiki/log.md.tpl wiki/log.md
mv wiki/overview.md.tpl wiki/overview.md
mv wiki/radar.md.tpl wiki/radar.md
# Si has_tracked_repos = true :
mv tracked-repos.config.json.tpl tracked-repos.config.json
```

Supprime les `.tpl` originaux qui ont été dupliqués (ils ont fait leur job) :

```bash
rm .claude/agents/domain-expert.md.tpl
rm wiki/domains/domain.md.tpl
rm .claude/agent-memory/domain-memory.md.tpl
```

### 5.7 Déplacement de `BOOTSTRAP.md` et `PLACEHOLDERS.md` en ADR

Trace consultable du bootstrap :

```bash
mv BOOTSTRAP.md wiki/decisions/bootstrap-prompt.md
mv PLACEHOLDERS.md wiki/decisions/placeholders-reference.md
```

### 5.8 Reset git + commit initial

```bash
rm -rf .git/
git init
git add -A
git commit -m "vault initial — généré via BOOTSTRAP.md le {{bootstrap_date}}"
```

---

## Section 6 — Étape 5, Remote GitHub optionnel

Pose :

```json
{
  "questions": [{
    "question": "Souhaites-tu créer un repo GitHub pour ton vault {{vault_name}} ?",
    "header": "Remote",
    "multiSelect": false,
    "options": [
      {"label": "✅ Oui, privé", "description": "gh repo create {{vault_name}} --private --source=. --push"},
      {"label": "✅ Oui, public", "description": "gh repo create {{vault_name}} --public --source=. --push"},
      {"label": "❌ Non, je gère manuellement", "description": "Aucune action. Tu pourras ajouter un remote plus tard avec git remote add origin <url>."}
    ]
  }]
}
```

Selon réponse :

- **Privé** : `gh repo create {{vault_name}} --private --source=. --push`
- **Public** : `gh repo create {{vault_name}} --public --source=. --push`
- **Manuel** : skip.

**Si `gh` n'est pas installé ou pas authentifié** (capture l'erreur du `gh repo create`) :
- Bascule en manuel.
- Affiche : « `gh` indisponible. Pour ajouter un remote plus tard : `gh auth login` puis `gh repo create {{vault_name}} --private --source=. --push`. »

**Gestion des erreurs `gh repo create`** :

- **Nom déjà pris** (« repository already exists ») : re-pose la question « Le nom `{{vault_name}}` est déjà pris. Quel autre nom utiliser ? (ou laisse vide pour skip le push) ».
- **Authentification expirée** (« HTTP 401 ») : afficher « `gh auth login` requis. Bascule en mode manuel : voici les commandes à lancer plus tard : `gh repo create <name> --private --source=. --push`. » et continue le bootstrap sans le remote.
- **Autre erreur** : afficher l'erreur brute + bascule en manuel comme ci-dessus.

---

## Section 7 — Étape 6, Récap onboarding final

Affiche un message texte propre :

```
🎉 Ton vault `{{vault_name}}` est prêt.

Identité : {{name}} — {{role}}
Domaines actifs ({{N}}) : {{ domain_1, domain_2, ... }}
Pipeline disponible : /ingest, /query, /save, /lint, /evolve-agent{{ ", /ingest-video" if ingest_video_enabled }}{{ ", /sync-repos" if has_tracked_repos }}

Trois prochaines actions guidées :

1. Dépose ta première source dans `raw/notes/<YYYY-MM-DD-sujet>.md` (ou `raw/transcripts/`, `raw/pdfs/`, etc. selon le format).
2. Lance `/ingest` — Claude proposera l'agent expert correspondant et tu valideras via AskUserQuestion.
3. Édite `wiki/overview.md` pour étoffer ton portrait : parcours, activités, intentions. Le draft généré n'est qu'un point de départ.

Trace du bootstrap : wiki/decisions/bootstrap-prompt.md (ce que tu viens de lancer) + wiki/decisions/placeholders-reference.md (mapping détaillé).

Bon ingest.
```

---

## Annexes

### A. Liste des fichiers générés (à titre de checklist mentale)

- `CLAUDE.md` (à la racine)
- `wiki/index.md`, `wiki/log.md`, `wiki/overview.md`, `wiki/radar.md`
- Pour chaque domaine : `wiki/domains/<slug>.md` + `.claude/agents/<slug>-expert.md` + `.claude/agent-memory/<slug>/MEMORY.md`
- `wiki/decisions/bootstrap-prompt.md`, `wiki/decisions/placeholders-reference.md`, `wiki/decisions/tiered-loading-wiki.md` (déjà présent)
- Conditionnels : `tracked-repos.config.json`, `wiki/decisions/tracked-repos-immutable-snapshots.md`, `wiki/decisions/extraction-frames-induction-runbook.md`, `wiki/decisions/ingest-video-modes-a-b-generalisation.md`
- `.git/` neuf, premier commit posé.

### B. Fichiers à NE PAS toucher

- `LICENSE`, `.gitignore`, `README.md` (le README peut être mis à jour par l'utilisateur lui-même plus tard pour son instance — ne le réécris pas pendant le bootstrap).
- `scripts/scan-raw.sh`, `scripts/backfill-summaries.py`, `scripts/enrich-hub.py` (génériques, restent tels quels).
- Les slash-commands non-conditionnels : `/ingest`, `/query`, `/save`, `/lint`, `/evolve-agent`.

### C. En cas de blocage

Si une étape de la Section 5 échoue (ex. un placeholder oublié dans un fichier, un `.tpl` qui ne se laisse pas substituer) :

1. Ne fais **pas** le `git init` final tant que tout n'est pas propre.
2. Affiche l'erreur précise à l'utilisateur, propose un fix manuel ou un retry de l'étape.
3. Le `.git/` original existe encore tant que 5.8 n'a pas été lancé — tu peux toujours `git diff` pour comparer à l'état initial.

Une fois le `git init` neuf fait, l'historique du template est perdu. C'est volontaire (clean start, cf. arbitrage Pierre 2026-04-30).

### D. Bloc SYNC-REPOS à injecter dans CLAUDE.md

Quand `has_tracked_repos = true`, copier ce bloc verbatim à la place du placeholder `{{sync_repos_section}}` dans CLAUDE.md.

````markdown
### SYNC-REPOS (`/sync-repos [noms]`)

Synchronise la doc de repos GitHub externes (frameworks, outils, projets que tu suis) vers `raw/`, en respectant strictement l'immutabilité.

**Manifest** : `tracked-repos.config.json` à la racine du vault. Champs par source :
- `name` (slug, clé d'invocation), `repo` (`owner/name` GitHub, ex. `vercel/next.js`, `nf-core/sarek`, `your-org/your-repo`), `branch` (typiquement `main`)
- `dest` (chemin relatif au vault, sans le `<shortsha>/`) — libre, à toi de définir l'arborescence
- `paths` (optionnel, défaut `default_paths` du manifest) — uniquement ces chemins sont copiés depuis le clone
- `exclude_paths` (optionnel, défaut `default_exclude_paths` du manifest) — chemins supprimés du snapshot **après** copie. `rm -rf` tolérant : un chemin absent est ignoré silencieusement.

Défauts au niveau racine : `default_paths` et `default_exclude_paths`. Ces défauts s'appliquent à toute source qui n'override pas explicitement.

**Principe snapshot par SHA.** Chaque sync crée `<dest>/<shortsha>/` (shortsha = 7 premiers chars du SHA du HEAD de `branch`). Si ce dossier existe déjà → skip. Un merge sur `main` côté GitHub = un nouveau SHA = un nouveau snapshot à côté de l'ancien. Les anciens snapshots ne sont **jamais** modifiés ni supprimés.

**Résolution de la cible** (main context) :
- aucun argument → multiSelect interactif (`AskUserQuestion`) sur les sources du manifest, pour éviter un « tout sync » involontaire.
- noms explicites (`next sarek`) → ces sources.

**Mécanique** (`scripts/sync-repos.sh`) :
1. `gh api repos/<repo>/commits/<branch>` → SHA du HEAD.
2. Si `<dest>/<shortsha>/` existe → `SKIPPED`.
3. Sinon : `gh repo clone --depth=1 -b <branch>` dans `cache/sync-repos/<name>/`, copie des `paths` listés vers `<dest>/<shortsha>/`, écriture de `.sync-meta.json` (repo, branch, sha, synced_at, paths), cleanup du clone.

**Chaînage sur `/ingest`.** Pour chaque ligne `CREATED <path>` remontée par le script : enchaîner `/ingest <path>` séquentiellement.

**Journalisation.** Entrée dans `wiki/log.md` :
```
## [YYYY-MM-DD] sync-repos | N snapshots créés
<liste>
```

**Ajouter un nouveau repo** : éditer `tracked-repos.config.json`, puis `/sync-repos <nouveau-name>`.
````

---

*Fin du prompt portable. Lance maintenant la Section 2.*
