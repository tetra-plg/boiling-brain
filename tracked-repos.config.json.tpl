{
  "$schema_note": "Manifest of GitHub repos to sync into raw/ via /sync-repos. Each sync creates a short-SHA snapshot (one per merge into main). See CLAUDE.md > SYNC-REPOS. Per-source fields: name (slug), repo (owner/name on GitHub), branch, dest (vault-relative path — typically raw/tracked-repos/<slug>), paths (optional, default = default_paths), exclude_paths (optional, default = default_exclude_paths) — paths removed from the snapshot after copy, relative to the repo root.",
  "default_paths": ["docs/", "README.md", "CHANGELOG.md"],
  "default_exclude_paths": [],
  "sources": []
}
