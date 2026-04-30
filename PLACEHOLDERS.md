# Placeholders reference — for the bootstrap prompt (Phase 4)

This file documents every `{{placeholder}}` used in the `*.tpl` files of this template, plus the cross-file dependencies. The Phase 4 bootstrap prompt is responsible for resolving these via a structured interview and producing the final files.

## Global placeholders (one value per instance)

| Placeholder | Type | Source / How to derive | Used in |
|---|---|---|---|
| `{{name}}` | string | Interview Q1 (full name) | `CLAUDE.md.tpl`, `overview.md.tpl`, `index.md.tpl` |
| `{{vault_name}}` | string | Interview Q (vault name, defaults to a slug of `{{name}}`) | `CLAUDE.md.tpl` |
| `{{role}}` | string | Interview Q (current role / title) | `CLAUDE.md.tpl`, `overview.md.tpl` |
| `{{parcours_short}}` | markdown bullet list, 2-4 lines | Interview Q (career, in 2-3 bullets) | `overview.md.tpl` |
| `{{bootstrap_date}}` | YYYY-MM-DD | `date +%Y-%m-%d` at bootstrap time | `overview.md.tpl`, `index.md.tpl`, `radar.md.tpl`, `domain.md.tpl` (per-domain) |
| `{{has_factory_repos}}` | boolean | Interview Q (do you want to track GitHub repos via `/sync-factory-docs`?) | Conditional: keeps or removes `factory-docs.config.json.tpl`, `scripts/sync-factory-docs.sh`, `.claude/commands/sync-factory-docs.md`, `wiki/decisions/factory-docs-immutable-snapshots.md`, and several blocks inside `CLAUDE.md.tpl` |

### Conditional sections in `CLAUDE.md.tpl`

These are filled or removed based on `{{has_factory_repos}}` and other flags:

| Placeholder | When `false` | When `true` |
|---|---|---|
| `{{slash_commands_extras}}` | `` (empty) | `, /sync-factory-docs` |
| `{{factory_docs_arborescence}}` | `` | `  factory-docs/      # snapshots par SHA des composants core (<composant>/<shortsha>/)\n  factory-projects/  # snapshots par SHA des projets générés (<projet>/<shortsha>/)\n` |
| `{{factory_repos_cache}}` | `` | `  factory-repos/       # clones --depth=1 temporaires utilisés par /sync-factory-docs, purgés en fin de sync\n\n` |
| `{{factory_scripts_extras}}` | `` | `, sync-factory-docs` |
| `{{sync_factory_docs_section}}` | `\n` | full `### SYNC-FACTORY-DOCS` section copied from the reference instance |

## Domain-driven placeholders (one set per declared domain)

The bootstrap prompt loops over the domains the user declared (3-6 typically) and instantiates **one file per loop iteration** for each of:

- `.claude/agents/<domain_slug>-expert.md` (from `domain-expert.md.tpl`)
- `wiki/domains/<domain_slug>.md` (from `domain.md.tpl`)
- `.claude/agent-memory/<domain_slug>/MEMORY.md` (from `agent-memory/domain-memory.md.tpl`)

Per-domain placeholders:

| Placeholder | Type | Source | Used in |
|---|---|---|---|
| `{{domain_slug}}` | kebab-case slug | Interview (e.g. `poker`, `ai`, `astro-physics`) | all three files |
| `{{domain_label}}` | human label | Interview (e.g. `Poker`, `AI`, `Astronomy & Physics`) | all three files |
| `{{is_hub_pivot}}` | boolean | At most one domain marked hub-pivot | `domain.md.tpl`, `domain-expert.md.tpl` |
| `{{hub_pivot_marker}}` | string | If `is_hub_pivot` → ` **Domaine pivot** : irrigue les autres domaines.` else `` | `domain.md.tpl` |
| `{{summary_l0}}` | ≤140 chars | LLM-generated from the domain description | `domain.md.tpl` frontmatter |
| `{{summary_l1}}` | 2-5 sentences | LLM-generated from the domain description | `domain.md.tpl` frontmatter |
| `{{domain_intro_paragraph}}` | 1-2 lines | LLM-generated short intro (« Hub dédié à X. Y. ») | `domain.md.tpl` |
| `{{taxonomy_section}}` | bullet list of sub-topics | Interview (3-8 sub-themes per domain) | `domain.md.tpl` |
| `{{related_domains_section}}` | optional H2 with cross-refs | Computed from cross-domain dependencies declared at interview | `domain.md.tpl` |
| `{{deliverables}}` | YAML list | Interview (e.g. `[cheatsheets, syntheses]`) | `domain-expert.md.tpl` |
| `{{deliverables_signature_block}}` | markdown block describing the agent's signature deliverable | Built from `{{deliverables}}` | `domain-expert.md.tpl` |
| `{{trigger_examples}}` | comma-separated list | LLM-generated from the domain description (4-6 verbal triggers for visual frames) | `domain-expert.md.tpl` |
| `{{frames_visual_formats}}` | markdown bullet list | LLM-generated from the domain (e.g. `Mermaid diagrams`, `LaTeX equations`, `13×13 grids`) | `domain-expert.md.tpl` |
| `{{co_ingest_partners}}` | list of domain slugs | Interview (per domain, which other domains often share sources?) | `domain-expert.md.tpl` |
| `{{co_ingest_section}}` | markdown block | Built from `{{co_ingest_partners}}`; empty if no partners | `domain-expert.md.tpl` |
| `{{authority_table_enabled}}` | boolean | True for "reflexive" domains where source authority matters (AI, science, industry analysis) | `domain-expert.md.tpl` |
| `{{authority_table_section}}` | markdown block | Built from `{{authority_table_enabled}}`; empty otherwise | `domain-expert.md.tpl` |
| `{{confidentiality_block}}` | markdown block | Filled if the domain involves sensitive data (typically work / management); empty otherwise | `domain-expert.md.tpl` |
| `{{confidentiality_section}}` | markdown block | `{{confidentiality_block}}` wrapped in an H2 heading; empty if no sensitivity flag | `domain-expert.md.tpl` |
| `{{domain_specific_observation_section}}` | markdown bullet list | LLM-generated from the domain's typical "what you watch for in a source" angles (calqued on poker-expert / ia-expert in the reference instance) | `domain-expert.md.tpl` |
| `{{model}}` | `sonnet` or `haiku` | Interview / heuristic on domain density (dense reflexive domains → sonnet) | `domain-expert.md.tpl` frontmatter |
| `{{effort}}` | `high` or `medium` | Same heuristic | `domain-expert.md.tpl` frontmatter |
| `{{maxTurns}}` | `60` or `80` | Same heuristic | `domain-expert.md.tpl` frontmatter |

## Cross-domain placeholders (computed from the full domain list)

| Placeholder | Type | Computation | Used in |
|---|---|---|---|
| `{{domains_section}}` | numbered markdown list with one-line descriptions | Iterate over domains | `CLAUDE.md.tpl` |
| `{{domains_index_section}}` | bullet list of `[[domains/<slug>]]` links | Iterate over domains | `index.md.tpl` |
| `{{domains_links}}` | bullet list (same idea, slightly different formatting) | Iterate over domains | `overview.md.tpl` |
| `{{projects_links}}` | bullet list of personal projects | Interview Q (do you have personal projects to declare in `overview.md`?) — if none, use a placeholder « (à compléter) » | `overview.md.tpl` |
| `{{agents_section}}` | bullet list of `<domain>-expert` with their signature deliverable | Iterate over domains | `CLAUDE.md.tpl` |

## Total

- **Global placeholders** (instance-wide): 6 + 5 conditional sections = **11**
- **Per-domain placeholders**: 17 per domain instance × N domains
- **Cross-domain placeholders** (computed from full domain list): 5

The bootstrap prompt's job is to:
1. Run a structured interview filling the global + per-domain inputs.
2. Compute the cross-domain placeholders from the collected data.
3. For each `*.tpl` file, substitute placeholders and write to the final path (renaming to drop the `.tpl` suffix).
4. Loop over the domain-driven templates, instantiating one file per declared domain.
5. Apply the conditional removal of factory-docs files if `{{has_factory_repos}} = false`.

## Notes for the Phase 4 prompt author

- The unified `domain-expert.md.tpl` was fused from 5 reference instance prompts (poker, ia, metier, tech, astro-physique). The structural skeleton is shared; what varies is the domain-specific observation section, frame triggers, frame formats, deliverable signature, and a few conditional blocks (authority table, co-ingest, confidentiality).
- The factory-related artifacts are conditional, NOT a sixth domain. The factory-expert in the reference instance was deliberately excluded — the "evolving framework documentation" pattern was deemed too instance-specific to standardize.
- The bootstrap interview should ideally take 5-10 minutes for someone who has thought about their domains, longer otherwise. Don't over-engineer the interview — it's better to ship something opinionated and let the user evolve it via `/evolve-agent` after a few real ingestions.
