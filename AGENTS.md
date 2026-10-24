# AGENTS.md

Guidance for coding agents working in stream.

This file carries what an agent needs before it can act: what the project is and
how to build and test it. Everything else — conventions, engineering principles,
and the writing rules — lives in
[`.github/copilot-instructions.md`](.github/copilot-instructions.md), which is the
canonical instruction file. Read it next; this file deliberately does not repeat
it, so the two cannot drift apart.

## What this is

stream plays music on your local network, from your own files and from Bilibili.
A Python 3.14 server (FastAPI is planned) keeps its library in SQLite and serves a
React, Vite, and TypeScript web client from `web/`. Design notes live in
`docs/contributing/design-notes/`.

## Build and test

Python is managed by [uv](https://docs.astral.sh/uv/); the web client needs Node 24
and npm.

```bash
# Python server: install, then the same gates CI runs
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run bandit -q -c pyproject.toml -r src
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv run pip-audit -r <(uv export --locked --format requirements-txt --no-emit-project --quiet) --disable-pip --progress-spinner off   # needs network

# Web client
cd web && npm ci && npm run check && npm run build
npx playwright install chromium   # once, for e2e
cd web && npm run e2e
```

> [!IMPORTANT]
> Four details above are load-bearing, not decoration. `uv sync --locked` fails
> when `uv.lock` disagrees with `pyproject.toml`, so a dependency change always
> ships with its lock file. `ruff format --check` is a gate of its own: `ruff check`
> does not report formatting, so a clean lint is not a clean CI. And `mypy` runs in
> strict mode over `src` and `tests`; a test that is not annotated fails it. Coverage
> floors are 90% line and 85% branch, enforced in CI from the JSON report
> ([`CONTRIBUTING.md`](CONTRIBUTING.md#coverage) explains them). Finally, `pip-audit`
> reads the locked dependency set, not the active environment, and a known
> vulnerability in it fails CI ([`CONTRIBUTING.md`](CONTRIBUTING.md#security-checks)).

## Read next

| Document | What it covers |
| --- | --- |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Conventions, engineering principles, and the path-specific rules below. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Full setup, coverage, the web client, and the pull-request checklist. |
| `docs/contributing/design-notes/` | The design notes: one per component, recording goal, decisions, and tradeoffs. |
| [`README.md`](README.md) | Project overview and status. |

Path-specific rules apply automatically in GitHub Copilot; other agents should
read whichever matches the files they touch:

- [`.github/instructions/python.instructions.md`](.github/instructions/python.instructions.md) — Python server and tests.
- [`.github/instructions/web.instructions.md`](.github/instructions/web.instructions.md) — the `web/` client.
- [`.github/instructions/docs.instructions.md`](.github/instructions/docs.instructions.md) — the `docs/` tree, including how to add a design note.
