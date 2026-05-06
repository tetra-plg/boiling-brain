---
description: Query the wiki to answer a question from indexed pages, with citations and optional synthesis archiving
argument-hint: <question>
---

Run the QUERY workflow from CLAUDE.md on: $ARGUMENTS

1. Read `wiki/index.md` to identify the pages relevant to the question.
2. Read those pages, follow the necessary `[[wikilinks]]`.
3. Synthesize the answer with `[[page]]` citations.
4. If the answer is substantial, suggest archiving it into `wiki/syntheses/<slug>.md`.
5. Append to `wiki/log.md`: `## [YYYY-MM-DD] query | <short question>`.
