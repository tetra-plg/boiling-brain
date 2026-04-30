{
  "$schema_note": "Manifest des repos GitHub à synchroniser vers raw/ via /sync-factory-docs. Chaque sync crée un snapshot par SHA court (merge sur main). Voir CLAUDE.md > SYNC-FACTORY-DOCS. Champs par source : name (slug), repo (owner/name GitHub), branch, kind (core|project), dest (chemin relatif au vault), paths (optionnel, défaut = default_paths), exclude_paths (optionnel, défaut = default_exclude_paths) — chemins à supprimer du snapshot après copie, relatifs à la racine du repo.",
  "default_paths": ["README.md", "docs/", "CHANGELOG.md"],
  "default_exclude_paths": [],
  "sources": []
}
