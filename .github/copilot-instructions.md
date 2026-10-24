# medleyplay — Copilot instructions

medleyplay plays music on your local network, from your own files and from Bilibili.
A **Python 3.14 server** (FastAPI is planned) keeps its library in **SQLite** and
serves a **React + Vite + TypeScript** web client from `web/`. The domain core —
the library, playback, and the rules that connect them — is plain Python with no
web or downloader imports; web frameworks, yt-dlp, and SQLite sit at the edges.

Path-specific rules live alongside this file and apply automatically:

- [`.github/instructions/python.instructions.md`](instructions/python.instructions.md) — Python server and tests.
- [`.github/instructions/web.instructions.md`](instructions/web.instructions.md) — the `web/` client.
- [`.github/instructions/docs.instructions.md`](instructions/docs.instructions.md) — the `docs/` tree and design notes.

## Build and test

Python is managed by [uv](https://docs.astral.sh/uv/) (`pyproject.toml`, `uv.lock`,
`.python-version`); the web client uses Node 24 and npm.

```bash
# Python server
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run bandit -q -c pyproject.toml -r src
uv run mypy
uv run pytest --cov --cov-report=term-missing   # coverage floors: see CONTRIBUTING.md
uv run pip-audit -r <(uv export --locked --format requirements-txt --no-emit-project --quiet) --disable-pip --progress-spinner off   # needs network

# Web client
cd web && npm ci && npm run check && npm run build
cd web && npm run e2e   # needs: npx playwright install chromium
```

VS Code tasks (**Terminal → Run Task**) mirror these: `sync`, `lint`, `security: bandit`, `security: audit`, `typecheck`,
`test`, `coverage`, `web: check`, `verify: all`, and more.

`ruff format --check` is the formatting gate and CI runs it before the linter.
`ruff check` does not report formatting, so a clean lint alone does not mean a green
CI. Plain `uv run pytest` runs the tests in parallel without coverage; add `--cov`
when you change tested behavior.

## Conventions

- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/); one
  logical change each; mark breaking changes with `BREAKING CHANGE:` in the footer.
- **Tests:** test-driven — write a failing test first, then the code, then refactor.
  Python uses pytest and Hypothesis; the web client uses Vitest and Playwright.
- **Fully typed Python:** every function and method is annotated and
  `mypy --strict` passes. `Any` appears only with a stated reason; prefer precise
  types — `Protocol`, `TypedDict` or a dataclass, `Literal`, `NewType`, `Final`,
  `Self`. The toolchain is pytest, mypy, and ruff, with Hypothesis and pytest-cov.
- **Design first for non-trivial work:** design notes live in
  `docs/contributing/design-notes/`; read the relevant ones before changing a
  component, and add or update one when a decision changes.
- **American English** in code, comments, docs, and commit messages.
- **Keep the core free of the edges:** no FastAPI, yt-dlp, or HTTP-client imports in
  the domain core (see [Engineering principles](#engineering-principles)).
- **Never commit secrets.** Credentials and a Bilibili login stay in the ignored
  `.env` or a cookies file; the library database and audio cache stay out of git.

## Comments

The code is the first documentation. Before adding a comment, try a better name or
a small, well-named helper; a comment explaining *what* tangled code does is a
signal to refactor it. When a comment is still needed, it:

- **is true now.** It describes the code as it is. A reversed decision leaves no
  trace, and there is no history: no "previously", "no longer", or "for now".
- **stands alone.** No issue or PR numbers, no design-note paths or decision labels,
  and no other type named as the reason. The design note holds the argument; the
  comment holds the fact.
- **reads once.** Plain words a developer new to the project understands on first
  reading (see the word list below).
- **states the fact, not the argument.** It leaves out the route not taken and
  warnings about misuse.
- **shows an example.** A parser shows the input it handles, a function the values
  it takes and returns, and a flow a small diagram:

  ```python
  def split_title(text: str) -> tuple[str, str]:
      """Split a track name into its artist and title.

      "Joe Hisaishi - Summer" gives ("Joe Hisaishi", "Summer").
      """
  ```

Tests follow the same rules. The language files add the conventions for
[Python](instructions/python.instructions.md#docstrings-and-comments) and
[TypeScript](instructions/web.instructions.md#comments).

Words that read two ways or are figurative:

| Avoid | Write | Why |
| --- | --- | --- |
| peel | split off, remove | figurative |
| weave | join, meet again | figurative |
| surface (as a verb) | report, show | figurative |
| seam | interface, or name the thing | figurative |
| lands, lands on | enters, opens, is in range | figurative |
| rides, rides along | is carried, holds | figurative |
| owed | needs, still has to | figurative |
| clobber | overwrite | slang |
| wedge | leave stuck, block | figurative |
| lockstep | in sync | figurative |
| minted | assigned, created | figurative |
| umbrella, apparatus, scaffolding | name the thing | says nothing about what it is |
| lifts (a value, some text) | copies, takes | figurative |
| lights up | highlights | figurative |
| summons | opens | figurative |
| outranks | overrides, takes precedence over | figurative |
| adrift | unattached | figurative |
| spoken for | already claimed | idiom |
| signpost (as a verb) | mark | figurative |
| upheld | guaranteed, kept | figurative |

## Engineering principles

Decision heuristics for changes here:

- **Readable first.** Follow the spirit of the Zen of Python — simple over
  complex, explicit over implicit, readable over clever. When readability and
  performance conflict, choose readability unless performance is genuinely
  critical (it rarely is); avoid premature optimization.
- **Model the domain (DDD) and keep one ubiquitous language.** Code, tests, and
  docs share one vocabulary taken from the domain — a track, a library, a source,
  a queue — and a name is a design decision, not an afterthought. Value objects
  and entities are typed (`NewType`, frozen dataclasses), not bare strings and
  dicts. When the vocabulary changes, change it everywhere at once.
- **Ports and adapters.** The core defines what it needs as `Protocol` ports
  (a track source, a library store, a clock); adapters implement them at the edge
  for SQLite, the local file system, Bilibili through yt-dlp, and HTTP through
  FastAPI. Dependencies point inward: the core never imports an adapter, a web
  framework, yt-dlp, or `sqlite3`.
- **Test-driven and pyramid-shaped.** Mostly fast unit tests, fewer integration
  tests, minimal end-to-end; strive for 100% meaningful coverage. Treat tests as
  code and refactor them too.
- **Tests are the live specification.** A reader learns what the code does from its
  tests: a name states the behavior, input is shown in the domain's own notation,
  and a helper hides only what the test does not care about. The rules are in
  [Tests](instructions/python.instructions.md#tests).
- **SOLID, patterns applied judiciously.** Use a pattern only where it removes
  real duplication or coupling. Add a `Protocol` where behavior is likely to
  change — but avoid premature generalization and over-abstraction (YAGNI).
- **Law of Demeter — tell, don't ask.** Send messages to your own collaborators,
  not to objects reached through them. This governs objects with behavior, not
  data: reading across immutable value objects (`track.album.title`) is fine.
- **Enforce architecture with tests.** Guard the dependency direction above with
  architecture tests built on [import-linter](https://import-linter.readthedocs.io/),
  not hand-rolled import scans: for example, the core must not import `fastapi`,
  `yt_dlp`, `sqlite3`, or any adapter package. The tool joins the project with the
  first domain package; until then the rule is kept in review.
- **Prefer established solutions over hand-rolling.** Survey the mature, maintained,
  license-compatible packages before writing parsing, retries, validation, or
  scheduling yourself; keep the core dependency-light.
- **Refactor relentlessly** while the tests stay green, and **respect the
  conventions already in this repo.**

## Source of truth

Point at these rather than restating them, so instructions never drift from the
docs:

- **[`CONTRIBUTING.md`](../CONTRIBUTING.md)** — full development setup, coverage,
  the web client, and the pull-request checklist.
- **`docs/contributing/design-notes/`** — the design of each component.
- **[`README.md`](../README.md)** — project overview and status.

[`AGENTS.md`](../AGENTS.md) at the repository root is the entry point for other
agent tools. It carries only what an agent needs before it can act — what the
project is and how to build and test it — and points here for the rest, so the
two files cannot drift apart.
