---
description: File a sanitized issue on the upstream template repo from the current session context (auto-sanitizes vault-specific data)
argument-hint: [bug|enhancement|docs|question] [<short optional description>]
---

Run the CREATE-ISSUE workflow on: $ARGUMENTS

This command files a bug, an enhancement, a docs request or a general question to the **upstream template repo** (`tetra-plg/boiling-brain` by default). It generates a draft from the conversation context, **sanitizes** vault-specific data via the rules in `.claude/rules/sanitization-issues.md`, shows a preview, then creates the issue via `gh issue create`.

No silent creation: the final step is always a user validation via `AskUserQuestion`.

## 1. Pre-requisites

Check in this order, stop at the first failure with a clear message:

```bash
# 1.1 — gh CLI authenticated
gh auth status 2>&1 | head -5
# On failure: "Run `gh auth login` then re-run /create-issue."

# 1.2 — template-upstream remote configured (if missing, propose it)
TEMPLATE_REMOTE_URL=$(git remote get-url template-upstream 2>/dev/null)
if [ -z "$TEMPLATE_REMOTE_URL" ]; then
  echo "The template-upstream remote is not configured."
  echo "Configure it via:"
  echo "  git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git"
fi
```

Extract `<owner/repo>` from the remote URL (parse `https://github.com/<owner>/<repo>.git` or `git@github.com:<owner>/<repo>.git`). Store in `TEMPLATE_REPO`.

## 2. Issue type determination

Parse `$ARGUMENTS`:

- First token = type, among `bug`, `enhancement` (alias `feature`), `docs`, `question`.
- Rest = optional short description to pre-fill the title.

If type missing or invalid → `AskUserQuestion`:

```json
{
  "questions": [
    {
      "question": "Which issue type do you want to create?",
      "header": "Type",
      "multiSelect": false,
      "options": [
        {
          "label": "bug",
          "description": "Something doesn't work as expected (sections: Context, Reproduction, Proposed fix, Test plan, Impact)"
        },
        {
          "label": "enhancement",
          "description": "Improvement or new feature (sections: Problem, Proposal, Alternatives, Out-of-scope, Done criteria)"
        },
        {
          "label": "docs",
          "description": "Gap or imprecision in template docs (sections: Section concerned, Gap observed, Suggestion)"
        },
        {
          "label": "question",
          "description": "Usage or design question (sections: Context, Question, What was already tried)"
        }
      ]
    }
  ]
}
```

GitHub label mapping: `bug` → `bug`, `enhancement` / `feature` → `enhancement`, `docs` → `documentation`, `question` → `question`. Verify the label exists on the target repo:

```bash
gh label list --repo "$TEMPLATE_REPO" --json name --jq '.[].name'
```

If the label doesn't exist, create the issue without label (signal in the preview to the user).

## 3. Context collection

Read the current conversation to identify the issue subject:

- Which file / behavior / scenario is at stake?
- Which observed-vs-expected error (for bug) / which gap (for enhancement / docs) / which point of confusion (for question)?
- Are there relevant code excerpts, error traces, or commands?

If the description from `$ARGUMENTS` is provided, use it as a **candidate title** but rephrase if it contains internal references (slugs, wikilinks).

## 4. Drafting per template

### Structure by type

**bug**:

```markdown
## Context

<2-3 sentences: where, in which scenario, since when>

## Reproduction

<Minimal reproducible steps. Command / file snippet if relevant.>

## Proposed fix

<Correction hypothesis. List of files / lines / approach.>

## Test plan

- [ ] <test case 1>
- [ ] <test case 2>

## Impact

<Blocking? Cosmetic? How many vaults affected?>
```

**enhancement**:

```markdown
## Problem

<Why the status quo is insufficient>

## Proposal

<Description of the proposed solution>

## Alternatives considered

<Other approaches, why discarded>

## Out-of-scope (v1)

<What is NOT done in this first version>

## Done criteria

- [ ] <criterion 1>
- [ ] <criterion 2>
```

**docs**:

```markdown
## Section concerned

<File + precise section (e.g. README.md "Workflow loop")>

## Gap observed

<What is unclear, missing, or wrong>

## Suggestion

<What could be added or rephrased>
```

**question**:

```markdown
## Context

<Configuration / scenario>

## Question

<The question, precisely formulated>

## What was already tried

<Resources read, tests run>
```

## 5. Sanitization

Apply the rules of `.claude/rules/sanitization-issues.md` to the title **and** body of the draft:

- **Silent strip**: wikilinks `[[...]]`, `raw/notes/YYYY-MM-DD-*` paths, domain slugs listed in `wiki/index.md`, `wiki/sources/<date>-<slug>.md` paths, emails.
- **Flag for review**: proper nouns mid-sentence (excluding whitelist `Claude`, `Anthropic`, `GitHub`, etc.), entity names read from `wiki/entities/*.md`, `@xxx` handles.
- **Anonymization of concrete cases**: rephrase "18 BB pages had X" as "N pages affected (figure measured on the BoilingBrain reference vault)" or "Some vault pages had X".

Build a **sanitization report** with:

- List of silent transformations applied (can be copied for audit).
- List of flagged elements awaiting user confirmation.

## 6. Preview and validation

Display in the format:

```
=== Issue draft (sanitized) ===

Target repo: tetra-plg/boiling-brain
Label: bug

Title:
<sanitized title>

Body:
<sanitized body>

=== Sanitization ===
Silent transformations:
- <wikilink> → <generic term>
- <slug> → domain X
- ...

To confirm (flagged):
- Proper noun detected: "<token>" — confirm or edit
- ...
```

Then `AskUserQuestion`:

```json
{
  "questions": [
    {
      "question": "What do you want to do with this draft?",
      "header": "Issue",
      "multiSelect": false,
      "options": [
        {
          "label": "✅ Create the issue",
          "description": "Creates the issue via gh issue create. Will return the URL."
        },
        {
          "label": "✏️ Edit manually",
          "description": "Doesn't create anything. Shows the draft ready to copy-paste into the GitHub UI."
        },
        { "label": "❌ Cancel", "description": "Aborts without creating anything." }
      ]
    }
  ]
}
```

## 7. Creation (if validated)

```bash
gh issue create \
  --repo "$TEMPLATE_REPO" \
  --title "$SANITIZED_TITLE" \
  --body "$SANITIZED_BODY" \
  --label "$LABEL"
```

Capture the returned URL (stdout). On failure (network, unknown label, insufficient rights): show the error + the copy-pastable draft as fallback.

## 8. Follow-up (radar)

After successful creation, propose via `AskUserQuestion`:

```json
{
  "questions": [
    {
      "question": "Add a tracker in wiki/radar.md?",
      "header": "Radar",
      "multiSelect": false,
      "options": [
        {
          "label": "✅ Yes, track in the radar",
          "description": "Adds an entry `- [ ] **[Template · YYYY-MM-DD]** <short description>. → <URL>` in wiki/radar.md \"To watch\" category"
        },
        {
          "label": "❌ No, no local follow-up",
          "description": "The issue lives its life on GitHub only"
        }
      ]
    }
  ]
}
```

If yes: append the entry to `wiki/radar.md`, dedicated commit `chore(radar): track upstream issue <#N>`.

Log in `wiki/log.md`: `## [YYYY-MM-DD] create-issue | <type> #<number> <short title>`.

## Proactive use case from the radar

`/create-issue` can also be triggered **proactively** by the main context when the radar is shown ("show me the radar" / "what's on the agenda today"). When a radar entry concerns the **template environment** (typically a bug or gap touching `scripts/wiki-maint/scan-raw.sh`, `.claude/commands/*.md`, `BOOTSTRAP.md`, or any file propagated by `/update-vault`), the main context proposes to the user:

> This radar entry concerns the upstream template. Want to file it via `/create-issue <type>`?

The main context **does not create the issue itself** — it just suggests the command, the user validates, and the standard workflow above takes over.

## Fallback if `gh auth login` is missing

If at step 1.1 `gh auth status` fails, do not continue. Show the sanitized draft ready to copy-paste (without even running full sanitization — just a raw draft). The user can then `gh auth login` and re-run, or copy-paste into the GitHub UI.
