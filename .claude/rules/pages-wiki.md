---
description: Conventions d'écriture des pages du wiki (style, slugs, callouts, structure)
paths:
  - "wiki/**"
---

# Pages wiki — conventions d'écriture

## Slug et nommage

- `kebab-case.md` strict pour tous les fichiers wiki.
- Pas d'accents, pas de majuscules, pas d'espaces, pas de caractères spéciaux dans les noms de fichiers.
- Une page = une idée / une entité / un concept / une décision. Si > 400 lignes, scinder.
- `wiki/sources/` : format `YYYY-MM-DD-slug.md` (date d'acquisition de la source).

## Liens internes

- Tous les liens internes en `[[wikilinks]]` style Obsidian.
- Format alias : `[[chemin/slug|Texte affiché]]` quand le slug n'est pas explicite.
- Pas de chemins relatifs `../` pour les pages wiki — toujours wikilinks.
- Liens externes via syntaxe markdown standard `[texte](url)`.

## Callouts Obsidian

Pour signaler explicitement les contradictions et incertitudes :

```markdown
> [!warning] Contradiction
> Source A dit X, source B dit Y. Pas de résolution actuelle.

> [!question] Incertitude
> Le mécanisme exact de Z n'est pas documenté dans les sources lues.
```

- `[!warning]` pour une contradiction factuelle entre sources ou avec le wiki existant.
- `[!question]` pour une incertitude non résolue, à élever vers `wiki/radar.md`.

## Style

- Français pour les titres, le corps, les explications. Termes techniques en VO si l'usage VO est dominant.
- Ton **neutre** pour `entities/`, `concepts/`, `cheatsheets/`. Plus personnel pour `overview.md`, `wiki/domains/*.md`.
- Listes et tableaux courts > paragraphes longs.
- Toujours citer les sources : champ `sources:` du frontmatter + `[[source-slug]]` inline pour un claim précis.
- Pas de longues introductions. Pas de méta-commentaire ("Cette page va vous expliquer...").

## Cross-références

Une section `## Cross-refs` à la fin de chaque page substantielle, listant les pages connexes :

```markdown
## Cross-refs

- [[concepts/<lié>]] — angle complémentaire.
- [[decisions/<liée>]] — choix d'archi qui s'applique.
- [[sources/<source>]] — source primaire.
```

## Seuil de création de page

- **≥ 2 sources** mentionnent le concept indépendamment, OU
- jugé structurant par l'utilisateur (validation explicite).

Pas de page pour chaque concept mentionné en passant.
