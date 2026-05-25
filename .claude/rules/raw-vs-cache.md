---
description: Immutability principle of raw/ and transient role of cache/
paths:
  - "raw/**"
  - "cache/**"
---

# raw/ vs cache/ — immutability principle

## raw/ — strictly immutable

`raw/` contains the **raw sources** the wiki references. Every `wiki/sources/<slug>.md` page points to a `raw/` file via its `source_path` frontmatter.

Hard rules:

- **Never modify an existing file in `raw/`.** If a source evolves (e.g. doc updated), create a **new file** with a new SHA, never overwrite the old one.
- **Never move a file out of `raw/`** once it is referenced by a wiki page: you would break `source_path` and `source_sha256`.
- **SHA-keyed snapshots** for evolving sources (cf. [template doc — tracked-repos-immutable-snapshots](https://github.com/tetra-plg/boiling-brain/blob/main/docs/tracked-repos-immutable-snapshots.md)): each version → a new dedicated folder, never overwrite.
- **No expert agent writes to `raw/`.** Agents read `raw/` and write to `wiki/`. The only exception is frame promotion (`cache/frames/` → `raw/frames/`) handled by `/ingest-video`.

## cache/ — transient

`cache/` contains processing artifacts **never referenced by the wiki**. Purgeable at any time without loss of information.

Hard rules:

- **Never reference `cache/` from a wiki page.** Its content may disappear. If a `cache/` artifact must persist, it gets **promoted** to `raw/` (e.g. a frame retained for illustration).
- **Videos and audios** transit through `cache/videos/`, `cache/audio/` for the time of transcription, then are deleted or archived outside the vault.
- **Candidate frames** live in `cache/frames/`. Only the frames **actually used** by a wiki page are promoted to `raw/frames/<source-slug>-<descriptor>.png`.

## Practical consequences

- An agent that wants to cite a visual → make sure it is in `raw/frames/`, otherwise request promotion.
- A wiki coherence check (`/lint`) must flag any page that references a `cache/` path as an error.
- `raw/` is **safely git-versionable** (immutable by construction). `cache/` can be `.gitignored` if too large.

## Cross-refs

- [template doc — tracked-repos-immutable-snapshots](https://github.com/tetra-plg/boiling-brain/blob/main/docs/tracked-repos-immutable-snapshots.md) — SHA-keyed snapshot pattern for evolving external sources.
- [template doc — extraction-frames-induction-runbook](https://github.com/tetra-plg/boiling-brain/blob/main/docs/extraction-frames-induction-runbook.md) — promotion workflow `cache/frames/` → `raw/frames/`.
