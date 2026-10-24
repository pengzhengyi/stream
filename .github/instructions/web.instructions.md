---
applyTo: "web/**"
---

# Web client conventions

The client is a **React + Vite + TypeScript** project in `web/`, managed with npm.
You need **Node 24+** to work on it. Full context is in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Workflow

Run from `web/`:

```bash
npm ci
npm run dev      # live-reloading dev server
npm run check    # typecheck + eslint + stylelint + prettier + vitest
npm run build    # typecheck and build the production bundle
npm run e2e      # Playwright end-to-end (needs: npx playwright install chromium)
```

## Rules

- **Run `npm run check` before committing.** It must pass — it is the same gate CI
  runs. `npm run build` and `npm run e2e` run in CI too.
- Let the tooling format and lint: follow `eslint.config.js`, `.stylelintrc.json`,
  and `.prettierrc.json` rather than hand-formatting or overriding rules inline. A
  rule suppression gets a comment saying why.
- **TypeScript is strict.** No `any`; type external data where it enters the client.
  Use function components and hooks; the `react-hooks` rules are errors.
- Write tests for behavior: **Vitest** and Testing Library for components, queried
  the way a user finds things (by role and label), and **Playwright** for flows that
  need a real browser. A test name states the behavior it checks.
- Tests are deterministic: no real timers or network. Mock the server API at the
  `fetch` boundary.
- Quality tools keep content-aware incremental data under the ignored `.cache/`.
- Keep the client free of secrets; it only ever talks to the stream server.

## Comments

The shared rules — true now, standing alone, plain words, the fact rather than the
argument, an example — are in
[`copilot-instructions.md`](../copilot-instructions.md#comments). In the client:

- A module opens with a one- or two-sentence `@file` comment saying what it does.
- **TSDoc** (`/** */`) documents exported functions, components, and types whose
  purpose is not obvious. The first sentence says what it is.
- A CSS rule gets a comment only for a layout reason the selector does not show,
  stated as it holds now.
- **End-to-end tests** describe the condition a test guards ("on a 360-pixel-wide
  screen the queue stays reachable"), not the bug it once was. A viewport size, a
  wait, or a retry gets a comment when its reason is not visible.
