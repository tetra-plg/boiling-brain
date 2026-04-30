---
type: decision
domains: [meta]
created: 2026-04-29
updated: 2026-04-30
sources: []
summary_l0: "Extraction frames vidéo longues : sampling dense + image-diff + induction croisée transcript + validation batch + transcription markdown"
summary_l1: |
  Ce runbook décrit un process en 9 étapes pour extraire les frames pertinentes des vidéos longues (>30 min) où les méthodes simples sous-extraient. Chaque étape croise plusieurs signaux : sampling dense, calcul de différences de pixels, catalogage visuel par agent, validation contre le transcript (±30s), extraction en haute résolution, validation manuelle batch, puis transcription markdown du contenu. Applicable à tous les domaines du wiki. Recommandé pour vidéos denses ou soupçon de sous-extraction.
---
# Runbook — Extraction de frames par induction croisée (sampling × image-diff × transcript × validation manuelle × transcription markdown)

> Asset cross-domaine. Réutilisable par tous les agents experts du wiki. Les particularités domaine (UI logiciels spécifiques, profils OCR, formats de cheatsheets) sont reléguées dans la section **Annexes domaine** en fin de runbook.

## Problème

Les vidéos longues (>30 min) — coachings, conférences, démonstrations logicielles, tutoriels UI, replays commentés — alternent slides, captures d'écran, schémas et face caméra. Les méthodes simples ratent des frames :

- **Frame requests directes par l'agent expert** (mode léger `/ingest-video`) : sous-extraction systématique sur les vidéos denses. L'agent ne « voit » rien — il infère depuis le transcript des phrases comme « regardez ce tableau », mais rate les visuels affichés sans verbe explicite, ou inverse, sur-extrait des frames sans contenu pédagogique unique.
- **Image-diff seuil global** : rate les transitions subtiles (changement de couleur dans une grille, pop-up de menu, slide « build animé »). Aussi : promeut des frames « jolies mais pas pédagogiques ».
- **Catalogage visuel exhaustif sans transcript** : promeut des doublons (le même visuel pendant 2 minutes de discussion = 1 seule frame utile, pas 10).

→ Besoin d'un process qui **croise plusieurs signaux** et garde l'humain dans la boucle pour les décisions ambiguës — et qui produit du **markdown interrogeable** pour chaque frame, pas juste une image.

## Options écartées

- **Tout extraire toutes les 5 s** : 800–1000 frames par vidéo, ingérable manuellement, énorme bruit.
- **Délégation totale à un agent** : sans validation humaine, biais systématiques (ex: l'agent garde tout ce qui est « nouveau » même quand c'est une variante triviale d'un slide précédent).
- **Image-diff seul** : voir Problème.
- **Transcript seul (frame requests)** : voir Problème.
- **Image-only (PNG sans transcription markdown)** : sans transcription, chaque `/query` doit ré-analyser l'image, perd l'indexation grep/search, augmente le coût récurrent.

## Décision retenue : process en 9 étapes

### Étape 1 — Sampling dense

**But** : matérialiser sur disque suffisamment de candidats pour que l'image-diff trouve toutes les transitions.

**Cadence par défaut selon le type de vidéo** :

| Type de vidéo | Cadence | Volume samples typique |
|---|---|---|
| Coaching dense (slides matriciels, grilles, démos UI rapides) | toutes les 20 s | 100–250 |
| Conférence / talk avec slides texte | toutes les 30 s | 60–150 |
| Démo logicielle / tutoriel UI | toutes les 20–30 s | 80–200 |
| Interview / talking-head ponctué | toutes les 60 s | 30–80 |
| Quiz / slides courts | toutes les 60 s | 30–60 |

**Commande standard** (packagée dans [scripts/sample-frames.sh](../../scripts/sample-frames.sh)) :
```bash
scripts/sample-frames.sh "$VIDEO" /tmp/<slug>-samples/ [cadence_seconds]
```

Sortie : PNG 1280×720 dans le dossier de samples, plus un fichier `.cadence` mémorisant la cadence pour l'étape 2.

### Étape 2 — Image-diff filtering

**But** : éliminer les samples redondants (face caméra continue, slide stable).

**Méthode** : pour chaque paire `(sample_n, sample_n+1)`, calculer la différence moyenne des pixels gris. Optionnellement restreindre le calcul à un **ROI** (zone d'intérêt) pour ignorer une zone immuable (incrustation, watermark, webcam fixe).

**Commande** (packagée dans [scripts/diff-frames.py](../../scripts/diff-frames.py)) :
```bash
scripts/diff-frames.py /tmp/<slug>-samples/ \
  [--roi x,y,w,h] \
  [--threshold 12.0] \
  --output /tmp/<slug>-transitions.md
```

**ROI par défaut : `0,0,1,1`** (plein cadre, pas d'exclusion). N'utilise un ROI personnalisé que si tu sais qu'une zone précise n'apporte pas d'information visuelle pertinente — voir la section **Annexes domaine** pour des ROI documentés par cas d'usage. Ne pas appliquer un ROI « standard » à l'aveugle, c'est une source de faux négatifs.

**Seuil par défaut : `12.0`**. Plus bas → plus de transitions retenues (et plus de bruit). Plus haut → on rate les transitions subtiles.

Sortie : `/tmp/<slug>-transitions.md`, tableau `# | sample_path | timestamp_estimé | diff_mean`. Réduction typique ×3 à ×5 par rapport aux samples.

### Étape 3 — Catalogage visuel (agent Explore)

**But** : pour chaque transition, classer le visuel et décider GARDER / DOUBLON / SKIP.

**Délégation à un agent `Explore`** par vidéo (parallélisable en background si plusieurs vidéos en lot). Prompt type :

```
Pour chaque frame transition dans /tmp/<slug>-transitions.md :
- Lire la PNG.
- Classer le type de visuel : SLIDE TEXTE / TABLEAU / SCHÉMA / CAPTURE UI / CODE / DASHBOARD / PHOTO / FACE CAMÉRA / TRANSITION / AUTRE.
- Décrire le contenu en 1 ligne (ex. "Tableau comparatif 4 colonnes : nom outil, latence, prix, hit rate").
- Verdict : GARDER (contenu unique pédagogique) / DOUBLON (variante mineure de la précédente) / SKIP (face cam, transition pure, contenu non-pédagogique).
- Slug suggéré (kebab-case) si GARDER.

Output : tableau markdown avec colonnes # | timestamp | type | description | verdict | slug suggéré.
```

Pour les domaines avec heuristiques de reconnaissance UI propres (voir Annexes domaine), enrichir le prompt avec ces heuristiques.

### Étape 4 — Induction croisée frames × transcript

**But critique** : valider chaque frame `GARDER` en regardant **ce que dit le formateur ±30 s autour du timestamp**.

Pour chaque frame `GARDER` du tableau d'étape 3 :
- Extraire la fenêtre transcript `[t-30s, t+30s]`.
- Annoter : citation principale (verbatim court), concept abordé, justification (pourquoi cette frame mérite extraction).
- Si la fenêtre transcript ne mentionne **aucun élément pédagogique justifiant la frame** → **DOWNGRADE en SKIP** même si marquée GARDER au catalogage.

**Bénéfices** :
- Évite les frames « jolies mais pas pédagogiques ».
- Permet d'attacher une citation à chaque frame promue (réutilisable directement dans la transcription markdown étape 9).
- Garantit que les vidéos sont couvertes proportionnellement à leur richesse pédagogique réelle.

**Output** : tableau consolidé `/tmp/<slug>-induction.md` — **contrat d'extraction**. Colonnes : `# | timestamp | type | description | citation transcript | concept | verdict final | slug`.

### Étape 5 — Extraction 1080p natif

Re-extraction depuis le fichier source aux timestamps validés, en pleine résolution :

```bash
ffmpeg -nostdin -i "$VIDEO" -ss 00:HH:MM:SS -frames:v 1 -q:v 1 \
  /tmp/<slug>-finals/<slug>.png -y
```

`-ss` **APRÈS** `-i` pour précision frame-perfect. Sur des vidéos très longues (>25 min de seek), un mode pragmatique met `-ss` avant `-i` pour gagner du temps au prix d'une précision moindre.

### Étape 6 — Validation manuelle batch

**But** : trancher les ambiguïtés finales et capter les nuances que les agents ratent.

**Mode batch unique** (préféré pour réduire les interruptions) :
- Toutes les frames extraites présentées en une seule `AskUserQuestion` multiSelect.
- Options par frame : Promouvoir / Doublon / Skip / Re-extraire (±5 s).
- Le main context lit chaque PNG (vision Claude) et présente une description textuelle synthétique pour aider l'utilisateur à trancher sans ouvrir manuellement chaque image.

**Mode frame-par-frame** (fallback pour les vidéos à forte ambiguïté) :
- `open /tmp/<slug>-finals/<frame>.png` → ouverture dans Preview.
- `Read` la frame → description.
- `AskUserQuestion` une par une.

**Cadence observée** : ~30–60 s par décision en frame-par-frame → ~80–150 min pour 150 frames. Le mode batch divise typiquement par 3–4.

### Étape 7 — Promotion physique vers `raw/frames/`

Pour chaque frame « Promouvoir » :
```bash
cp /tmp/<slug>-finals/<frame>.png \
   raw/frames/YYYY-MM-DD-<source-slug>-<slug-final>.png
```

### Étape 8 — Re-spawn agent expert (re-ingest forcé)

Re-spawner l'agent expert du domaine en **re-ingest forcé** sur la page source, avec en contexte :
- La liste des frames promues (chemins `raw/frames/...`).
- Le tableau d'induction (citation transcript ±30 s + concept par frame).
- Instruction explicite d'enrichir les pages du wiki concernées (`wiki/sources/`, `wiki/concepts/`, `wiki/cheatsheets/`, `wiki/syntheses/`) avec ces frames.
- Instruction explicite de **transcrire chaque frame en markdown** (Étape 9).

L'agent expert reste libre de ses choix éditoriaux (quelle frame va dans quelle page, quel concept mérite une page nouvelle, etc.) — le runbook lui fournit les frames + leur contexte pédagogique, pas un plan de pages.

### Étape 9 — Transcription markdown du contenu visuel

**But fondamental** : rendre le contenu de chaque frame **interrogeable comme du texte**. Sans transcription, chaque `/query` doit ré-analyser l'image (coût récurrent, pas de grep/search). C'est le livrable principal côté wiki — l'image PNG n'est que le justificatif.

Pour chaque frame promue, l'agent expert ouvre le PNG (`Read`) et écrit la transcription dans la page wiki qui consomme la frame. Format selon le type de visuel :

| Type | Format de transcription | Exemple structurel |
|---|---|---|
| **Tableau / grille** | Markdown table reproduisant ligne par ligne, colonne par colonne | `\| col1 \| col2 \|` |
| **Schéma / diagramme** | Mermaid si la topologie le permet, sinon liste structurée nœuds + relations | ` ```mermaid\ngraph TD ... ` ou `- Nœud A → Nœud B (relation)` |
| **Code / terminal** | Bloc de code avec langage détecté, reproduit le contenu lisible | ` ```python\n... ` ou ` ```bash\n... ` |
| **Dashboard / KPI** | Liste markdown des indicateurs avec valeurs et unités | `- Latence p95 : 312 ms` |
| **Slide texte** | Titre + bullets, reproduction littérale | `### <titre>\n- bullet 1\n- bullet 2` |
| **Photo / illustration** | Description sémantique : sujet, composition, légende si visible | « Photographie d'un télescope, légende visible "M51 — 60 min de pose" » |
| **Capture UI** | Description structurée : zones de l'interface, boutons / champs / valeurs visibles | `Panneau gauche : liste de N items. Panneau droit : formulaire avec 3 champs (X, Y, Z).` |

**Règle non-optionnelle** : une frame promue sans transcription markdown est un défaut d'ingest. Si l'agent ne peut pas transcrire (image illisible, zoom insuffisant, ambiguïté irréductible), il l'indique en `> [!question]` plutôt que de laisser l'image orpheline.

**Bonus** : la citation transcript ±30 s extraite à l'Étape 4 doit être citée à côté de la transcription markdown — la double couche (visuel transcrit + verbatim formateur) maximise la valeur des futures `/query`.

## Heuristiques de reconnaissance visuelle (générique)

Signaux qui orientent vers `GARDER` plutôt que `DOUBLON` ou `SKIP` à l'Étape 3 :

- **Texte structuré nouveau** à l'écran (titre, headers de tableau, bullets de slide) absent des frames précédentes.
- **Transition de slide explicite** (bandeau, animation, numéro de slide).
- **Surimpression / annotation** ajoutée par le présentateur (entoure une zone, flèche, highlight).
- **Capture d'un logiciel différent** (changement d'interface, nouveau menu, pop-up).
- **Changement de page / onglet** dans une démo navigateur.
- **Graphique / chiffre nouveau** affiché.

Signaux qui orientent vers `DOUBLON` :
- Variante minime du slide précédent (curseur déplacé, barre de progression avancée, valeur incrémentée).
- Même slide commenté dans la durée.

Signaux qui orientent vers `SKIP` :
- Face caméra, fond de bibliothèque, transition pure (fondu, écran noir).
- Slide intro / outro sans contenu pédagogique.

Pour des heuristiques propres à un logiciel ou un format de cours spécifique, voir **Annexes domaine** ci-dessous.

## Quand appliquer ce process (Mode B)

- Vidéo > 30 min avec ≥ 10 visuels distincts attendus.
- Vidéo où on suspecte que `/ingest-video` mode léger (frame requests par l'agent) sous-extrait : densité de mentions visuelles élevée dans le transcript mais peu de frame requests déclarées par l'agent.
- Première vidéo d'un nouveau format pour un domaine (calibration des heuristiques avant scaling).
- Re-extraction d'une vidéo dont les frames ont été perdues / sont en basse résolution / il manque la transcription markdown.

## Quand NE PAS appliquer

- Vidéo conceptuelle parlée (talking head, podcast, interview audio-only) → `/ingest-video` mode léger suffit, l'agent expert déclare 2–4 frame requests si nécessaire.
- Vidéo < 15 min avec ≤ 3 visuels → frame requests manuelles plus rapides.

## Outils existants à réutiliser

- [scripts/transcribe.sh](../../scripts/transcribe.sh) — Whisper local (mlx-whisper).
- [scripts/sample-frames.sh](../../scripts/sample-frames.sh) — Étape 1.
- [scripts/diff-frames.py](../../scripts/diff-frames.py) — Étape 2.
- [scripts/extract-frames.sh](../../scripts/extract-frames.sh) — extraction one-shot (mode A `/ingest-video`).
- [/ingest-video](../../.claude/commands/ingest-video.md) — orchestrateur, propose mode A / B / Skip.
- `AskUserQuestion` — validation interactive batch.

## Questions ouvertes

- **Automatiser l'étape 4 (induction transcript)** : un agent peut-il générer le tableau croisé sans biais ? À tester sur plusieurs domaines.
- **Étape 6 batch full-multiSelect** : sur des batchs de 50+ frames sans ambiguïté (ex. quiz 100 % GARDER), un mode pure batch sans question par frame serait acceptable.
- **Transcription markdown automatisée par type** : peut-on déléguer à un agent visuel sans que la qualité chute ? Test sur tableaux, schémas, dashboards.

---

## Annexes domaine

Particularités à appliquer à l'Étape 2 (ROI), Étape 3 (heuristiques de reconnaissance UI) et post-Étape 7 (post-traitement) selon le domaine de la vidéo.

> Cette section est volontairement légère dans le template. À mesure que tu ingères des vidéos d'un domaine, ajoute ici les ROI utiles, les heuristiques UI, les profils OCR ou les formats de cheatsheet que tu finiras par découvrir empiriquement. Une bonne entrée d'annexe nomme **un format de vidéo précis** (« coaching X avec webcam fixe en bas-gauche »), pas un domaine entier.

### Annexe — `<your-domain>`

À enrichir au fil des ingests. Heuristiques candidates initiales :

- **Captures d'interface logicielle** : nouvelle conversation, nouveau panneau → GARDER systématique.
- **Diagrammes d'architecture / topologie** : nœuds + flèches → reproduire en Mermaid à l'Étape 9.
- **Graphes de benchmark / pricing / observation** : axes + courbes → transcription en tableau de valeurs ou description sémantique.

Duplique cette annexe pour chacun de tes domaines déclarés au bootstrap.
