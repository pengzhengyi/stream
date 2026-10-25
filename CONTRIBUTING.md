# Contributing to medleyplay

Thank you for considering a contribution. medleyplay is early stage, so small,
well-scoped changes are easiest to review and merge.

## Ways to contribute

- Report bugs with a minimal reproduction.
- Propose features or design changes.
- Improve documentation.
- Add tests for current behavior.
- Fix small, focused issues.

## Before you start

1. Search existing issues and pull requests to avoid duplicate work.
2. Open an issue for larger behavior or design changes before writing code.
3. Keep pull requests small and focused.

## Development setup

Requirements:

- [uv](https://docs.astral.sh/uv/) (it installs the Python version in
  `.python-version` itself)
- Node 24 and npm, for the web client
- Git

Clone the repository and run:

```bash
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run bandit -q -c pyproject.toml -r src
uv run mypy
uv run pytest
uv run pip-audit -r <(uv export --locked --format requirements-txt --no-emit-project --quiet) --disable-pip --progress-spinner off   # needs network
```

`ruff format --check` is the formatting gate and CI runs it first. `ruff check` does
not report formatting, so a clean lint alone does not mean a green CI. Run
`uv run ruff format` and `uv run ruff check --fix` to apply the fixes ruff can make.
`uv sync --locked` fails when `uv.lock` disagrees with `pyproject.toml`; after a
dependency change, run `uv lock` and commit the lock file with it.

Run the server's package from the command line with:

```bash
uv run python -m medleyplay --version
```

### Coverage

```bash
uv run pytest --cov --cov-report=term-missing --cov-report=html
```

Coverage is measured on `src/medleyplay` only, with branch coverage on; the HTML report
is written to `htmlcov/`. CI fails below **90% line** or **85% branch** coverage,
and warns below 95% line. Branch coverage is gated too because a decision point can
be fully line-covered with only one of its paths ever taken — a gap a line-only gate
cannot see. The line target stops short of 100% because some lines cannot be reached
by any test.

### Type checking and linting

`mypy` runs in strict mode over `src` and `tests`: every function and method is
annotated, and `Any` appears only with a stated reason. `ruff` selects every rule
and excludes only the ones that conflict with the formatter or with this project's
conventions; each exclusion in `pyproject.toml` has its reason beside it. Complexity
limits (cyclomatic complexity 10, 7 parameters, 40 statements) fail the lint.

### Security checks

ruff stays the formatter and linter; its `S` rules already include most of bandit's
checks. Two tools add what ruff does not:

- **bandit** scans `src` for insecure code, configured under `[tool.bandit]` in
  `pyproject.toml`. Tests are excluded because they use `assert`.
- **pip-audit** checks the dependencies pinned in `uv.lock` against the Python
  Packaging Advisory Database and exits non-zero when one has a known
  vulnerability. `uv export` feeds it the locked, hashed set, so it audits exactly
  what `uv sync --locked` installs rather than whatever is in the active
  environment. It needs network access and a shell that supports `<( )` (bash, zsh).

When pip-audit reports a vulnerability, upgrade the dependency with `uv lock
--upgrade-package <name>` and commit `uv.lock`. A fix that does not exist yet is a
decision for the pull request: name the advisory and the reason in the description
rather than silencing the check.

### Properties, beside examples

Most tests are **example-based**: one input, one expected output. That specifies
behavior, and it cannot state a rule that must hold for *every* input.
[Hypothesis](https://hypothesis.readthedocs.io/) property tests cover those: a round
trip, an invariant, "never raises". Add a property when a rule holds across all
inputs and no single example can say so, and keep the strategy producing inputs the
domain could plausibly produce.

A failing property has found a real counterexample, not a flake. Fix the code and
add the shrunk input as an example test in the same change, so the case stays
checked whatever later runs sample.

### Adding or updating a Python dependency

```bash
uv add <package>             # runtime dependency
uv add --group dev <package> # development tool
```

Commit `pyproject.toml` and `uv.lock` together. Prefer an established, maintained
package to hand-written code, especially outside the domain core.

### Web client (`web/`)

The client is a React + Vite + TypeScript project. You need Node 24+ to work on it:

```bash
cd web
npm ci
npm run dev                        # live-reloading dev server; /api goes to port 8000
npm run check                      # typecheck, lint, style, format, unit tests
npm run build                      # build the client into the Python package
npx playwright install chromium    # once, for e2e
npm run e2e                        # Playwright end-to-end tests
```

`npm run dev` forwards `/api` to a server you start yourself with
`uv run medleyplay serve`. `npm run check` is the gate CI runs for the **Frontend
quality** job; the **Frontend E2E** job runs `npm run e2e`, which builds the client
and starts the real server, so it needs `uv sync --locked` first. The server runs
on port 4174 over a fresh data folder and generated music in `web/.cache/e2e`. When an end-to-end test
fails in CI, download the `playwright-report` artifact from the run and open it with
`npx playwright show-report <folder>` for the trace and screenshot.

### Markdown

Every Markdown file is linted by
[markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2), configured by
[`.markdownlint-cli2.yaml`](.markdownlint-cli2.yaml). Run it from the repository
root with no arguments — the config carries the globs and the ignores, so the bare
command lints exactly what CI's **Docs** job does:

```bash
markdownlint-cli2
```

Links between files, including heading anchors, are checked offline by
[lychee](https://lychee.cli.rs/), configured by [`lychee.toml`](lychee.toml):

```bash
lychee --config lychee.toml --offline --no-progress "**/*.md"
```

### Spelling

Every file is spell-checked by [cspell](https://cspell.org), configured by
[`cspell.json`](cspell.json), whose `words` list carries the project's own
vocabulary and the tools and formats the docs cite:

```bash
npx --yes cspell@8 lint --no-progress --config cspell.json .
```

A real misspelling belongs in the text, not the dictionary: only genuine vocabulary
— a cited tool, a proper noun — earns a `words` entry.

### Editor tasks (VS Code)

Common tasks are wired up in `.vscode/tasks.json` (**Terminal → Run Task**), so you
can run them without memorizing commands: `sync`, `format: verify`, `format: fix`,
`lint`, `security: bandit`, `security: audit`, `typecheck`, `test`, `test: file`,
`coverage`, `web: install`, `web: build`, `web: check`, `web: e2e`, `verify: all`
(everything CI runs), `docs: lint markdown`, `docs: check links`,
`docs: check spelling`, and `clean`. The recommended extensions
are in `.vscode/extensions.json`.

## Guardrails

- **Secrets stay out of git.** Credentials and a Bilibili login belong in the
  ignored `.env` or a cookies file; `.gitignore` also keeps the library database and
  audio cache out. Check `git diff --staged` before you commit.
- **The core stays free of the edges.** The domain core imports no web framework,
  downloader, or database driver; adapters at the edge implement the core's ports.
  Architecture tests will guard this once the first domain package lands.
- **Reproducible tests.** No real clock, unseeded randomness, or network in a test.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
docs: describe the library design
fix(library): handle an empty track title
test(queue): cover removing the playing track
```

Use one logical change per commit. Mark breaking changes with `BREAKING CHANGE:` in
the commit footer.

## Pull request checklist

Before opening a pull request:

- [ ] Add or update tests for behavior changes.
- [ ] Update documentation and design notes for changed behavior or decisions.
- [ ] Run `uv run ruff format --check`, `uv run ruff check`, and `uv run mypy`.
- [ ] Run `uv run bandit` and `uv run pip-audit` as in [Security checks](#security-checks).
- [ ] Run `uv run pytest --cov` and confirm coverage stays above the floors.
- [ ] If you changed `web/`, run `npm run check`, `npm run build`, and `npm run e2e`.
- [ ] If you changed Markdown, run `markdownlint-cli2` and the link check.
- [ ] Keep the pull request focused on one topic.
- [ ] Explain why the change is useful.

## Code of conduct

All participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a
conduct problem privately, see
[Enforcement](CODE_OF_CONDUCT.md#enforcement).
