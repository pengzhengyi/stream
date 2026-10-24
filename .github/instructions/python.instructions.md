---
applyTo: "**/*.py"
---

# Python conventions

Apply to the server and its tests. Full setup and the pull-request checklist are in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md); the design of each component lives in
`docs/contributing/design-notes/`.

## Style

- **ruff is the formatter and the linter.** Follow what `ruff format` and
  `ruff check` report rather than fighting them; the rule set and the reason for
  each exclusion are in `pyproject.toml`. Line length is 100. ruff stays the
  formatter (it is black-compatible) and its `S` rules already cover most of
  bandit's checks, so no second formatter or linter is added.
- **Two security checks sit beside ruff.** `bandit` scans `src` for insecure code
  such as `shell=True`, unsafe deserialization, and weak hashes; tests are excluded
  because they use `assert`. `pip-audit` checks the dependencies pinned in `uv.lock`
  against known-vulnerability advisories and fails on a match. Fix a finding or
  upgrade the dependency; do not suppress it without a reason in a comment.
- **Imports at the top,** sorted by ruff; absolute imports from `medleyplay`.
- **Write self-documenting code.** Clear names, small functions, and good types
  carry the meaning so the code reads without narration. The rules for the
  comments that remain are in [Docstrings and comments](#docstrings-and-comments).
- Prefer comprehensions and `itertools` when they are a clear readability win over
  a loop; keep them simple, not clever. Use `pathlib` for paths and `match` for
  branching on shape.
- Four-space indent, LF line endings, UTF-8.

## Typing

Python here is fully typed.

- **Every function and method is annotated,** parameters and return, including in
  tests and fixtures. `mypy --strict` passes over `src` and `tests`.
- **`Any` appears only with a stated reason** in a comment. Reach for `object`, a
  `Protocol`, a `TypeVar`, or a precise union first. A `# type: ignore` names its
  error code and says why.
- **Prefer the precise type:** `Protocol` for a port, a frozen `dataclass` or
  `TypedDict` for structured data, `Literal` for a closed set of strings,
  `NewType` for an identifier that must not be mixed up, `Final` for a constant,
  `Self` for a method that returns its own type, and `Enum` when a set carries
  behavior. Avoid bare `dict` and `tuple` for domain data.
- Use the built-in generics and `X | None`, not `typing.List` or `Optional`.
- Parse external data (JSON, HTTP bodies, database rows) into typed values at the
  edge, so the core only ever sees typed objects.

## Docstrings and comments

The shared rules — true now, standing alone, plain words, the fact rather than the
argument, an example — are in
[`copilot-instructions.md`](../copilot-instructions.md#comments). In Python:

- A **module** opens with a one-line docstring saying what it holds.
- A **public class, function, or method** has a docstring in the Google style whose
  first line is one sentence saying what it is or does, in the imperative
  ("Return the track's duration."). Add a body only for what the signature cannot
  say: an example, a constraint a caller must keep, a reason the code cannot show.
- Do not restate the signature; types are annotated, so omit them from `Args:`.
  Document a parameter only when its meaning is not clear from its name.
- Show input in the domain's own notation inside the docstring, so it appears on
  hover.
- Leave a private helper undocumented unless its reason is not obvious.
- A `#` comment explains a reason the code cannot show — a protocol quirk, a
  workaround for a named library behavior — never what the next line does.

## Size and complexity

ruff enforces size and complexity limits; a violation fails CI.

| Guardrail | Limit | Rule |
| --- | --- | --- |
| Cyclomatic complexity | 10 | C901 |
| Function parameters | 7 | PLR0913 |
| Statements per function | 40 | PLR0915 |
| Branches per function | 12 | PLR0912 |

Split the function, introduce a parameter object, or simplify the branching; do not
suppress the rule. Keep a module under about 400 lines and split it by concept when
it grows past that.

## Design and errors

- Follow **SOLID** and **composition over inheritance**; reach for a pattern only
  when it removes real duplication or coupling.
- **Ports and adapters.** The core depends on `Protocol` ports and never imports
  FastAPI, yt-dlp, `sqlite3`, or an adapter package. Adapters implement the ports
  at the edge. Pass collaborators in through the constructor; do not reach for
  globals or module-level singletons.
- **Immutable by default:** frozen dataclasses for values, tuples and `Mapping`
  rather than lists and dicts in signatures that only read.
- **Law of Demeter, scoped to behavior.** Send a message to a direct collaborator
  rather than reaching through it; reading across immutable value objects is
  data navigation and is fine.
- Raise **specific exceptions** that name the offending input and the expectation,
  from a small hierarchy rooted in one project error type. Never use a bare
  `except:` or swallow an exception; catch the narrowest type, at the layer that
  can act on it.
- Treat time and randomness as dependencies: take a clock or a seeded
  `random.Random` as an argument instead of calling `datetime.now()` or `random`
  inside the core.

## Tests

- **Tests are production code and the live specification.** Hold them to the same
  standard; a reader should learn what the code does from its tests without opening
  it. Test-driven: a failing test first, then the minimum code, then refactor. A bug
  fix starts with a test that reproduces it.
- **pytest,** with plain functions and `assert`. Tests live in `tests/`, mirroring
  the layout of `src/medleyplay`, one file per module under test (`medleyplay/foo.py` →
  `tests/test_foo.py`). Tests run in parallel, so each must be independent.
- **The name states the behavior:** scenario and expected outcome, as a sentence
  (`test_version_flag_prints_the_installed_package_version`). The body states one
  behavior; arrange, act, and assert are separated by blank lines. Cover edge and
  error cases, not just the happy path.
- **DAMP over DRY.** A helper hides what the test does not care about; what the
  test is about stays visible at the call site, usually as an argument.
- **Show input in the domain's notation** as a multi-line string literal
  (`"""…"""`), so its real shape shows, not strings stitched with `\n`.
- **One Object Mother per type, named `XFactory`,** in a shared test-support module
  (`tests/support/`). The type under test and one-glance values are built directly;
  everything else comes from its factory, so a constructor change touches one file.
  Vary a standard instance with `dataclasses.replace` or an optional argument. Never
  write a second factory for a type; merge factories that have grown apart. A
  fixture beyond one obvious value comes from a helper named for the scenario, whose
  docstring shows the input in domain notation.
- **Fresh fixture by default.** Share only what is immutable, stateless, and
  measurably expensive. Never share mutable state.
- **Deterministic:** no real clock, unseeded randomness, network, or dependence on
  test order. Use `tmp_path` for files and in-memory SQLite for the database.
- **Test through the public surface.** Mock only at boundaries; a test that checks
  interactions documents the implementation, not the behavior. Prefer a fake that
  implements a port to a mock.
- **Assert structure, not serialized text.** Parse JSON and HTML and compare the
  parts; prefer `assert expected == actual` so a failure shows what differs.
  A custom assertion helper states a domain claim and checks everything the inline
  version checked together.
- **Properties beside examples.** Examples specify behavior; a
  [Hypothesis](https://hypothesis.readthedocs.io/) property states a rule that must
  hold for every input (a round trip, an invariant, "never raises"). Keep the
  strategy producing inputs the domain could plausibly produce, and add a shrunk
  counterexample as an example test in the same change.
- **Never weaken a test.** A refactored test still checks everything the old one
  did. When a change is not obviously equivalent, break the behavior once and watch
  the test fail.
- **Guard architecture with tests** built on import-linter once the first domain
  package exists; extend that suite when you add a layer or a boundary.

## Before pushing

Run what CI runs, from the repository root:

```bash
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run bandit -q -c pyproject.toml -r src
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv run pip-audit -r <(uv export --locked --format requirements-txt --no-emit-project --quiet) --disable-pip --progress-spinner off   # needs network
```

`uv run ruff format` and `uv run ruff check --fix` apply the fixes ruff can make.
CI fails below 90% line or 85% branch coverage; see
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#coverage).
