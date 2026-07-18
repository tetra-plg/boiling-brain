---
description: Show the radar and optionally delegate per-domain triage to domain experts
argument-hint: [domain — empty = show all; --triage forces delegation]
---

Show `wiki/radar.md` and, **selectively**, delegate per-domain triage to the domain experts.

## Default — show the radar (main context)

With no argument (or a light radar), just display, as the conversational "show me the radar" flow does today:

1. Read `wiki/radar.md`; group the open `- [ ]` entries by their `**[Domain · YYYY-MM-DD]**` tag.
2. Read the accumulated agent suggestions in `.claude/agents/*.suggestions.md`; summarize recurring signals and agents ready for `/evolve-agent`.
3. Present the open entries and the suggestions digest. **No delegation.**

## Selective delegation — per-domain triage

Delegation is **opt-in**, never the default. Trigger it when either:

- `$ARGUMENTS` names a domain (or `--triage`) → force delegation for the targeted domain(s), **or**
- a domain has **≥ 3 open entries** *and* a matching `.claude/agents/<domain>-expert.md` exists → propose delegating that domain's triage.

Below the threshold, or for a domain without an expert agent, triage stays in the main context.

### Steps

1. **Partition**: split the open `- [ ]` entries by domain tag. Keep only the domains that qualify (explicitly targeted, or ≥ 3 open entries with an expert agent).
2. **Spawn one expert per qualifying domain** (parallel if several), each with:
   - Its **slice** of radar entries (verbatim lines).
   - A fresh snapshot: `bash scripts/mcp/wiki-cli.sh scan-domain <domain>` pasted under `## Domain snapshot`.
   - The content of `.claude/agent-output-contract.md`.
   - Instruction: **read-side radar-triage mode** — return a `## Triage recommendations` block (`close` / `merge` / `defer` / `keep` per entry, with rationale and `[[link]]`). **Do not edit `wiki/radar.md`.**
3. **Aggregate**: collect the `## Triage recommendations` blocks. Present the consolidated recommendations, grouped by domain and by verb.
4. **Apply after validation** (main context writes, never the agent):
   - `close` → tick `[x]` or remove the entry per the radar convention.
   - `merge` → fold into the target entry/page, remove the duplicate.
   - `defer` → keep, annotate the revisit trigger.
   - `keep` → unchanged.
5. Append to `wiki/log.md`: `## [YYYY-MM-DD] radar-triage | <domains> (agents: <names>) — N closed · M merged · K deferred`.

## Notes

- Radar entries are already typed by domain (`**[Domain · YYYY-MM-DD]**`), so the partition is clean and cross-domain-free.
- The expert grounds its triage in its **domain memory** (`.claude/agent-memory/<domain>/MEMORY.md`) and **Domain orientation** (tiered loading, #71) — judgment the main context can't replicate.
- Overridable: ask to "just show the radar" to skip delegation entirely.
