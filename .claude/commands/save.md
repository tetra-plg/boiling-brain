---
description: Archive the current conversation synthesis into wiki/syntheses/
argument-hint: <slug>
---

Run the SAVE workflow from CLAUDE.md with slug: $ARGUMENTS

Steps:

1. Identify the latest substantial synthesis/answer in the conversation.
2. Create `wiki/syntheses/$ARGUMENTS.md` with frontmatter (`type: synthesis`, `created`, `domains`, `sources`).
3. Include `[[page]]` links to the cited pages.
4. Update `wiki/index.md` Syntheses section.
5. Append to `wiki/log.md`: `## [YYYY-MM-DD] save | $ARGUMENTS`.

## Final step — normalise markdown

After all pages are written/updated, format the produced markdown so it stays
consistent and the CI `format-check` job passes:

```bash
npx -y prettier --write "wiki/**/*.md"
```
