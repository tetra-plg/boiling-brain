{
  "$schema_note": "Manifest des repos GitHub à synchroniser vers raw/ via /sync-repos. Chaque sync crée un snapshot par SHA court (merge sur main). Voir CLAUDE.md > SYNC-REPOS. Champs par source : name (slug), repo (owner/name GitHub), branch, dest (chemin relatif au vault — typiquement raw/tracked-repos/<slug>), paths (optionnel, défaut = default_paths), exclude_paths (optionnel, défaut = default_exclude_paths) — chemins à supprimer du snapshot après copie, relatifs à la racine du repo.",
  "default_paths": ["docs/", "README.md", "CHANGELOG.md"],
  "default_exclude_paths": [],
  "sources": []
}
