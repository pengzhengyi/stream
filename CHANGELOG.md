# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Accounts and the catalog** — the server keeps Accounts, sessions, Tracks,
  Sources, and Playlists in SQLite with migrations. The first Account becomes the
  admin; the server has one Account unless the config file lets the admin create
  more. You sign in and out, or out everywhere, and a
  lost password is reset with `medleyplay reset-password`. Each Account has its
  own favorites, ratings, and Playlists. `medleyplay serve` runs the API. See the
  [Architecture](docs/contributing/design-notes/Architecture.md#accounts) note.
- **Plugins** — features arrive as plugins that run in a separate plugin host
  process, so a plugin that raises, hangs, crashes, or leaks can't take the
  server down. A plugin that fails to load is quarantined, and one that keeps
  failing is faulted until an admin resets it. `medleyplay.toml` in the data
  folder turns plugins on and off, `medleyplay serve --safe-mode` starts with
  all of them off, and `GET /api/plugins` shows each plugin's state. See the
  [Plugin host](docs/contributing/design-notes/Plugin%20host.md) note.
- **Jobs** — long work, such as a download or a scan, runs as a Job in a process
  of its own, one at a time per target. Jobs retry plugin faults with a growing
  delay, wait out network failures, survive a server restart, and can be
  cancelled or retried; `GET /api/jobs` lists them with their progress. See the
  [Jobs](docs/contributing/design-notes/Jobs.md) note.
- **Libraries** — an admin registers a folder or a zip archive of music, and a
  scan adds its songs to the catalog with their tags. Rescans read only what
  changed, follow files that moved, mark files that went away as missing, and
  take an unplugged drive offline without forgetting it. The `fsspec-library`
  and `tinytag-tags` plugins read the files. See the
  [Libraries](docs/contributing/design-notes/Libraries.md) note.

### Changed

- Renamed the project from stream to medleyplay.

### Removed

- **The 2019 prototype** — the Express server, the Create React App client, and
  the library-file builder are retired ahead of a rewrite. They remain in the git
  history.
