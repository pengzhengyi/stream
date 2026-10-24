# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Accounts and the catalog** — the server keeps Accounts, sessions, Tracks,
  Sources, and Playlists in SQLite with migrations. The first Account becomes the
  admin, who creates the others; you sign in and out, or out everywhere, and a
  lost password is reset with `medleyplay reset-password`. Each Account has its
  own favorites, ratings, and Playlists. `medleyplay serve` runs the API. See the
  [Architecture](docs/contributing/design-notes/Architecture.md#accounts) note.

### Changed

- Renamed the project from stream to medleyplay.

### Removed

- **The 2019 prototype** — the Express server, the Create React App client, and
  the library-file builder are retired ahead of a rewrite. They remain in the git
  history.
