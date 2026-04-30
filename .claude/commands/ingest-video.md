---
description: Ingest a video (local file or YouTube URL) via audio extraction, transcription, then domain-expert ingest
argument-hint: <chemin-ou-url> [--induction|--mode-a|--skip-frames|--resume]
---

Run the INGEST-VIDEO workflow from CLAUDE.md on: $ARGUMENTS

## Pipeline

### 1. Acquisition audio + transcription

**Si `--resume <slug>` est passé** : skip cette étape. Vérifier la présence de `raw/transcripts/YYYY-MM-DD-<slug>.md` (et meta associée) — si présent, passer directement à l'étape 2. Si absent → erreur explicite. Le mode `--resume` est utilisé quand la transcription a déjà été produite par un pipeline en amont (transcription distante, intervention manuelle, etc.).

**Sinon (flux standard)** :

- Si URL YouTube : `yt-dlp -x --audio-format m4a -o "cache/audio/<slug>.%(ext)s" <url>`.
- Si fichier local : déplacer dans `${LLMWIKI_VIDEO_CACHE:-cache/videos}/`, puis `ffmpeg -i <video> -vn -acodec copy cache/audio/<slug>.m4a`.
- Transcription locale (whisper.cpp ou mlx-whisper) → `raw/transcripts/YYYY-MM-DD-<slug>.md` avec timestamps. Utiliser `scripts/transcribe.sh` qui couvre déjà ces étapes pour les deux cas.
- Créer `raw/videos-meta/YYYY-MM-DD-<slug>.meta.md` (URL, durée, hash, emplacement).
- Purger `cache/audio/<slug>.m4a`.

#### Convention de stockage vidéo : `LLMWIKI_VIDEO_CACHE`

Variable d'environnement utilisée par `scripts/transcribe.sh`, `scripts/sample-frames.sh` et `scripts/extract-frames.sh` pour localiser les vidéos téléchargées :

- **Défaut** : `cache/videos/` (disque interne, à l'intérieur du vault).
- **Override** : exporter `LLMWIKI_VIDEO_CACHE` vers un disque externe ou un dossier dédié si le volume vidéo dépasse la capacité du disque interne.

Pour les vidéos non-YouTube téléchargées manuellement (extension navigateur, drag-and-drop), drop le fichier dans `cache/videos/inbox/` puis invoquer le pipeline avec ce chemin local.

#### Fallback Mode A si vidéo entière indisponible

Si la vidéo entière n'a pas pu être téléchargée (cas d'un cache externe non monté au moment d'un clip), le Mode A (frame requests, étape 4a) peut récupérer chaque frame à la demande via `yt-dlp --download-sections "*HH:MM:SS-HH:MM:SS+15"` (segment court de ~15s) puis `ffmpeg`. Le Mode B (induction croisée) requiert la vidéo entière — non possible en fallback.

### 2. Ingest standard sur le transcript

Enchaîner sur `/ingest <transcript_path>` → dispatch vers l'agent expert du domaine.

L'agent reçoit en plus du contexte standard la convention frames :

```
Convention frames (extrait CLAUDE.md) :
## Frame requests
- FRAME: HH:MM:SS | slug | Description précise du visuel attendu
Critères cumulatifs :
(1) Confirmation verbale explicite dans le transcript qu'un visuel est affiché.
(2) Un visuel = une frame : regrouper les références multiples au même visuel, ne déclarer qu'un seul timestamp (premier affichage complet).
Résultat attendu : 2-4 frames max par heure de vidéo (variable selon densité visuelle du domaine).
```

Tous les agents experts disposent d'une section `## Frames visuelles` dans leur prompt — ils peuvent donc retourner un bloc `## Frame requests` quel que soit le domaine.

### 3. Choix du mode d'extraction (proposition à l'utilisateur)

Après que l'agent expert a renvoyé son rapport, **proposer** le mode d'extraction adapté à cette vidéo via `AskUserQuestion`. Pas de bascule silencieuse.

**Override flags** (consommés en priorité, pas de proposition affichée) :
- `--induction` → force mode B (induction croisée).
- `--mode-a` → force mode A (frame requests de l'agent).
- `--skip-frames` → saute l'extraction.

**Signaux à calculer** avant la proposition :
- `duration_min` : durée de la vidéo en minutes (depuis le frontmatter `duration` du `.meta.md`).
- `visual_mentions` : count des occurrences de patterns visuels dans le transcript : `regardez`, `voilà`, `vous voyez`, `ce schéma`, `ce tableau`, `cette grille`, `ce diagramme`, `cette image`, `à l'écran`, `cette capture`, `ce dashboard`, `ce flux`, `cette pipeline`, `ce code`, `ce slide`, `ce graphique`, `cette courbe`, `cette photo`. Insensible à la casse.
- `mentions_per_min` : `visual_mentions / duration_min`.
- `frame_requests_count` : nombre d'entrées dans le bloc `## Frame requests` du rapport agent (0 si bloc absent).

**Recommandation calculée** :
- **Recommander Mode A** si : `frame_requests_count` > 0 et cohérent avec `visual_mentions` (cas typique : agent a déclaré 2-4 frames sur une vidéo conceptuelle, ou plus sur vidéo dense de configurations multiples).
- **Recommander Mode B** si :
  - `duration_min ≥ 30` ET `mentions_per_min ≥ 0.3` ET `frame_requests_count` ≤ 30 % du compte « attendu » (`visual_mentions / 3` comme heuristique grossière) → suspicion sous-extraction.
  - OU `visual_mentions ≥ 10` ET `frame_requests_count` == 0 (agent n'a déclaré aucune frame mais le transcript signale beaucoup de visuels).
- **Recommander Skip** si : `duration_min < 15` ET `visual_mentions == 0`.

**Présentation** (`AskUserQuestion`, single-select 3 options) :

```
Question : « Quel mode d'extraction de frames pour cette vidéo ?
Signaux : durée Xm · Y mentions visuelles · Z frame requests par l'agent
→ Recommandation : <Mode X> »

Options :
- Mode A — frame requests de l'agent (Z frames)
- Mode B — induction croisée (sampling + image-diff + transcript)
- Skip — pas d'extraction de frames
```

L'option recommandée est marquée « (Recommandé) » et placée en première position.

**Logging** : la décision finale (mode + signaux + override éventuel) est journalisée dans `wiki/log.md` sur la même ligne que l'ingest :
```
## [YYYY-MM-DD] ingest-video | <titre> (agent: <nom>, mode: A|B|skip, durée Xm, Y mentions, Z frames)
```

### 4a. Mode A — frame requests directes (pipeline existant)

Pour chaque ligne `FRAME: HH:MM:SS | slug | description` du bloc `## Frame requests` :

1. Extraire la frame : `./scripts/extract-frames.sh <video_path> <timestamp> cache/frames/<slug>.png`.
2. Afficher toutes les frames extraites à l'utilisateur en batch via `AskUserQuestion`.
3. Sur validation → `cp cache/frames/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
4. Sur rejet → proposer retentative à timestamp ±X s ou annoter `> [!question] Frame non extraite` dans la page source.
5. **Re-spawn de l'agent expert** sur la page source en re-ingest forcé, avec la liste des frames promues + leur citation transcript ±30 s. L'agent doit transcrire chaque frame en markdown dans la page wiki concernée (cf. section « Frames visuelles » de son prompt + Étape 9 du runbook).
6. Rapport : `Frames mode A : N promues · M rejetées`.

### 4b. Mode B — induction croisée

Suit le runbook [wiki/decisions/extraction-frames-induction-runbook.md](../../wiki/decisions/extraction-frames-induction-runbook.md) :

1. **Sampling dense** : `scripts/sample-frames.sh <video> /tmp/<slug>-samples/ <cadence>`. Cadence selon le type de vidéo (cf. tableau du runbook, défaut 20 s pour les vidéos denses, 30 s pour les talks, 60 s pour les quiz).
2. **Image-diff** : `scripts/diff-frames.py /tmp/<slug>-samples/ [--roi …] [--threshold …] --output /tmp/<slug>-transitions.md`. Le ROI n'est appliqué que si une **annexe domaine** du runbook le justifie pour ce type de vidéo ; sinon plein cadre par défaut.
3. **Catalogage visuel** : spawner un agent `Explore` avec le tableau de transitions et le prompt de l'Étape 3 du runbook → tableau classé `GARDER / DOUBLON / SKIP`.
4. **Induction transcript** : pour chaque frame `GARDER`, extraire la fenêtre transcript `[t-30s, t+30s]` et l'annoter (citation, concept, justification). Downgrade en `SKIP` si pas de justification pédagogique. Output : `/tmp/<slug>-induction.md`.
5. **Validation manuelle batch** : afficher le tableau d'induction à l'utilisateur en un seul `AskUserQuestion` multiSelect (Promouvoir / Doublon / Skip / Re-extraire). Le main context lit chaque PNG candidate et présente une description textuelle pour chaque option.
6. **Extraction 1080p** : pour chaque frame `Promouvoir` : `ffmpeg -nostdin -i <video> -ss <ts> -frames:v 1 -q:v 1 /tmp/<slug>-finals/<slug>.png -y`.
7. **Promotion** : `cp /tmp/<slug>-finals/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
8. **Re-spawn de l'agent expert** sur la page source en re-ingest forcé, avec : liste des frames promues, citation transcript ±30 s par frame, instruction explicite de **transcrire chaque frame en markdown** (Étape 9 du runbook) dans `wiki/sources/`, `wiki/concepts/`, `wiki/cheatsheets/`, `wiki/syntheses/` selon les livrables de l'agent.
9. Rapport : `Frames mode B : N promues · M skipped · K re-extraites`.

### 5. Mode SKIP

Si SKIP retenu : pas d'extraction de frames. Annoter dans la page source : `> [!info] Extraction de frames sautée — vidéo jugée non visuelle ou trop courte.`. Logger dans `wiki/log.md`.

### 6. Sort de la vidéo locale

Pour les vidéos locales (pas YouTube) : proposer suppression / archivage hors-vault (`~/Archive/llm-wiki-videos/`) / conservation (déconseillé). **Cette étape a lieu après l'extraction des frames** (mode A, mode B ou skip).

---

**Note** : le dispatch vers l'agent expert de domaine se fait via `/ingest` standard — aucun chemin court-circuit. L'agent reçoit la convention frames dans son contexte de spawn ; il dispose d'une section `## Frames visuelles` dans tous les domaines.
