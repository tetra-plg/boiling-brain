---
description: Hard sanitization rules before publishing an issue to the upstream template repo (avoids leaking vault data)
paths:
  - ".claude/commands/create-issue.md"
  - "scripts/migrations/*-create-issue*.md"
---

# Sanitization before `gh issue create` to the upstream template

When the user invokes `/create-issue` to file a bug or improvement upstream, the draft is generated from the current Claude Code session context. That context can contain user-vault-specific data (domain slugs, proper nouns, paths to private content, internal references). These rules define what must be stripped, transformed or flagged for human review **before** the issue is created.

## Strip rules (silent transformation)

The following patterns are **systematically transformed** in the draft's title and body:

### 1. Obsidian wikilinks

- Pattern: `\[\[.+?\]\]` (with or without `|` alias).
- Action: full strip, **or** replace with a generic term if the context is explicit (e.g. `[[concepts/llm-wiki]]` → `the LLM wiki concept`).
- Justification: wikilinks are vault-internal references with no value outside.

### 2. Private-content paths

- Pattern: `raw/notes/YYYY-MM-DD-<anything>.md`, `raw/transcripts/YYYY-MM-DD-<anything>.md`, `raw/clippings/<anything>.md`.
- Action: replace with a generic placeholder (`raw/notes/<example>.md`, `raw/transcripts/<example>.md`).
- Justification: file names often reveal the topic of a private note.

### 3. Vault-specific domain slugs

- Read the list of domains from `wiki/index.md` (`## Domains` section) or the `wiki/domains/*.md` file names.
- For every slug detected in the draft (textual mention or path `wiki/domains/<slug>.md`), replace with `domain X`, `domain Y`, etc., **unless** the slug matches a generic term expected in the template (`work`, `tech`, `ai` may stay if context demands — but rarely).
- Justification: domains are a personal projection of the vault.

### 4. `wiki/sources/<date>-<slug>.md` paths

- Pattern: `wiki/sources/[0-9]{4}-[0-9]{2}-[0-9]{2}-<slug>.md`.
- Action: replace with `wiki/sources/<example>.md` or with a functional description (`a source page about X`).
- Justification: reveals what the user has ingested recently.

## Flag rules (mandatory human review)

The following patterns are **not silently stripped** but flagged to the user in the preview, who must validate or edit them:

### 5. Person names

- Heuristic: any capitalized token in the **middle of a sentence** (excluding sentence start), except known whitelist (`Claude`, `Anthropic`, `GitHub`, `Linux`, standard OSS product names).
- Action: highlight in the preview with a warning "Person name detected: `<token>` — confirm or edit".
- Justification: a proper noun may be a real person from the vault (colleague, trainer, study subject). Automatic detection would have too many false positives for silent stripping.

### 6. Vault-specific external entity names

- Pattern: company names, internal products, non-public projects referenced in `wiki/entities/`.
- Action: read entity names from `wiki/entities/*.md` and flag every occurrence in the draft.
- Justification: an internal product or vault client must never go out publicly.

### 7. User identifiers (emails, handles)

- Pattern: `[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+`, `@[a-zA-Z0-9_]+` (potential handles).
- Action: silent strip for emails. Flag for handles (may be legitimate public references like `@anthropics`).

## Structural rules

### 8. Anonymizing concrete cases

If the draft cites a concrete case ("18 BB pages had..."), propose a neutral wording: "Some vault pages had..." or "N pages affected (figure measured on the BoilingBrain reference vault)". The template maintainer can choose to add the precision in the issue context, but the default wording is anonymous.

### 9. Templates per issue type

- **bug**: `## Context`, `## Reproduction`, `## Proposed fix`, `## Test plan`, `## Impact` sections.
- **enhancement** (alias `feature`): `## Problem`, `## Proposal`, `## Alternatives considered`, `## Out-of-scope`, `## Done criteria` sections.
- **docs**: `## Section concerned`, `## Gap observed`, `## Suggestion` sections.
- **question**: `## Context`, `## Question`, `## What was already tried` sections.

The draft follows one of these templates depending on the type. No free narrative section.

## Final verdict

Issue creation is **always validated by the user** via `AskUserQuestion` with 3 options: create, edit manually, cancel. No silent creation, even if all strip/flag rules pass. The human safety net stays mandatory.

If the user picks "edit manually", the issue is not created — a copy-pastable draft is shown for them to use in the GitHub UI.
