---
applyTo: "docs/**/*.md"
---

# Documentation conventions

The `docs/` tree holds the project's written design:

- **`docs/contributing/design-notes/`** — one design note per component, each
  recording the goal, key decisions, and tradeoffs, with a reading guide
  (`README.md`) that maps them.

## Writing

- **American English**; keep prose tight; use sentence-style headings and a table
  of contents on longer notes.
- **Write loanwords unaccented** — `facade`, not `façade` — so the ASCII text
  matches the code and the spell checker.
- **Link to the authoritative doc** rather than restating build steps, conventions,
  or API details — point at `CONTRIBUTING.md` or the design notes so the docs never
  drift.
- Use **Mermaid diagrams** to clarify flow, architecture, and state; keep each
  diagram small and maintainable. Prefer a diagram over a long paragraph when it
  reads faster.
- **Polish the writing:** active voice, short paragraphs, concrete examples. Keep
  Markdown clean for `markdownlint-cli2` and links valid for `lychee`.
- A design note opens with a status callout (`> [!NOTE]` proposed / in progress /
  implemented) and is written as the current design, not a changelog.
- **Describe only what ships.** A page must not advertise a capability the system
  does not have, and a status callout states what is built now — a feature that is
  planned, dormant, or superseded says so.
- **State a general property with an example,** not counts or full lists that drift
  as the code changes.
- **Reword rather than extend the dictionary.** When cspell flags a word you coined,
  a plainer phrase is usually clearer. Add a word to `cspell.json` only when it is a
  real name: a tool, a format, a proper noun.

## Design notes

- **One note per concept, named for the concept.** A follow-up to an existing
  design goes into that note's section; a new note is only for a concern the
  existing notes do not cover. Never name a note after the step that delivered it.
- **Present tense, no history.** A note records the design as it stands. Leave out
  issue and PR numbers, branch names, test counts, and delivery labels; git holds
  that history.
- Add each note to the reading guide, in reading order, in the section matching its
  folder.

## Checks

Run from the repository root before pushing:

```bash
markdownlint-cli2
lychee --config lychee.toml --offline --no-progress "**/*.md"
npx --yes cspell@8 lint --no-progress --config cspell.json .
```
