---
description: Format all markdown in the vault with Prettier (on-demand / one-shot normalisation)
argument-hint: [path-or-folder — empty = whole repo]
---

Normalise markdown formatting so it stays consistent across the whole wiki and
passes the CI `format-check` job.

Run Prettier in write mode on the target (default: the whole repo; `raw/` and
other paths are excluded via `.prettierignore`):

```bash
npx -y prettier --write "${ARGUMENTS:-**/*.md}"
```

Then confirm it is idempotent:

```bash
npx -y prettier --check "${ARGUMENTS:-**/*.md}"
```

Report the number of files reformatted. This command is also used for the
**one-shot** normalisation of a vault that predates the formatter (expect a
large diff the first time — review it stays cosmetic, then commit).
