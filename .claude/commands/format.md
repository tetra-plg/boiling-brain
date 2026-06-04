---
description: Format all markdown in the vault, Obsidian-safe (on-demand / one-shot normalisation)
argument-hint: [path-or-folder — empty = whole repo]
---

Normalise markdown formatting so it stays consistent across the whole wiki and
passes the CI `format-check` job.

Use the Obsidian-safe formatter (`scripts/wiki-maint/format-md.py`), which wraps
Prettier but masks the pipes inside wikilinks (`[[target|alias]]`) and code
spans (`` `a|b` ``) so Prettier cannot mistake them for table column separators
and corrupt the tables. `raw/`, `cache/`, `node_modules/`, `.git/`, `.obsidian/`
and `docs/superpowers/` are excluded automatically.

Run in write mode on the target (default: the whole repo):

```bash
python3 scripts/wiki-maint/format-md.py --write "${ARGUMENTS:-**/*.md}"
```

Then confirm it is idempotent:

```bash
python3 scripts/wiki-maint/format-md.py --check "${ARGUMENTS:-**/*.md}"
```

Report the number of files reformatted. This command is also used for the
**one-shot** normalisation of a vault that predates the formatter (expect a
large diff the first time — review it stays cosmetic, then commit).
