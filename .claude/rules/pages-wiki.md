---
description: Writing conventions for wiki pages (style, slugs, callouts, structure)
paths:
  - "wiki/**"
---

# Wiki pages — writing conventions

## Slug and naming

- Strict `kebab-case.md` for all wiki files.
- No accents, no uppercase, no spaces, no special characters in file names.
- One page = one idea / one entity / one concept / one decision. If > 400 lines, split.
- `wiki/sources/`: format `YYYY-MM-DD-slug.md` (date the source was acquired).

## Internal links

- All internal links as `[[wikilinks]]` Obsidian-style.
- Alias format: `[[path/slug|Display text]]` when the slug is not self-explanatory.
- No relative `../` paths for wiki pages — always wikilinks.
- External links via standard markdown syntax `[text](url)`.

## Obsidian callouts

To explicitly flag contradictions and uncertainties:

```markdown
> [!warning] Contradiction
> Source A says X, source B says Y. No current resolution.

> [!question] Uncertainty
> The exact mechanism behind Z is not documented in the sources read.
```

- `[!warning]` for a factual contradiction between sources or against the existing wiki.
- `[!question]` for an unresolved uncertainty, to bubble up to `wiki/radar.md`.

## Style

- Vault language (declared as `{{vault_language}}` in `CLAUDE.md`) for titles, body, explanations. Technical terms in VO when the VO usage is dominant.
- **Neutral** tone for `entities/`, `concepts/`, `cheatsheets/`. More personal for `overview.md`, `wiki/domains/*.md`.
- Short lists and tables > long paragraphs.
- Always cite sources: `sources:` field in frontmatter + `[[source-slug]]` inline for a specific claim.
- No long introductions. No meta-commentary ("This page will explain...").

## Cross-references

A `## Cross-refs` section at the end of every substantial page, listing related pages:

```markdown
## Cross-refs

- [[concepts/<related>]] — complementary angle.
- [[decisions/<related>]] — applicable architectural choice.
- [[sources/<source>]] — primary source.
```

## Page-creation threshold

- **≥ 2 sources** mention the concept independently, OR
- judged structural by the user (explicit validation).

No page for every concept mentioned in passing.
