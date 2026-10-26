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
- **Playing audio** — `POST /api/tracks/{id}/playback` picks the Source a
  Track plays from, and its audio is served with Range, `If-Range`, and `HEAD`,
  so browsers, Safari included, can seek. A song compressed in a zip archive is
  copied into the cache once by a Job and answers *preparing* until then. Plays
  are recorded under ids the client chooses, so a retry counts once, and each
  Track says whether it can play now. See the
  [Playback](docs/contributing/design-notes/Playback.md) note.
- **Web player** — the server serves a web player at `/`: sign in, or create the
  first Account on a new server; the Track list; a queue you can reorder; and a
  player with seeking and lock-screen controls. Each browser keeps its own queue
  and position across reloads, and counts a play as Last.fm does. Build it with
  `npm run build` in `web/`. See the
  [Playback](docs/contributing/design-notes/Playback.md#the-web-client) note.
- **A redesigned web player** — a floating player with icons for every control,
  a light, dark, or system theme, and a queue you reorder by dragging, or from
  the keyboard. The seek bar is easier to drag and moves the Track only once
  let go, and a row's actions show on touch screens.
- **The song table** — sort by any column, hide and resize columns, and mark
  favorites and rate Tracks from five stars, in the table and the player. It
  draws only the rows on screen, so a large Library scrolls smoothly. Each Track
  in the API now says whether it is `downloaded`. See the
  [Web client](docs/contributing/design-notes/Web%20client.md) note.
- **Play modes** — shuffle, and repeat the queue or the current Track, saved
  with the queue. Choosing a Track now queues its whole list, so *Previous*
  reaches the Tracks before it. See the
  [Playback](docs/contributing/design-notes/Playback.md#the-web-client) note.
- **Bilibili** — save an Account's Bilibili login from a cookies file, kept in
  the macOS Keychain and lent to its downloads; look a video up by any link,
  short links included, and add its parts as Tracks, which download in the
  background and play even after the video is removed. The `bilibili` plugin is
  off by default until yt-dlp can read Bilibili again. See the
  [Bilibili](docs/contributing/design-notes/Bilibili.md) note.
- **Job progress over SSE** — `GET /api/events` tells every open browser each
  time a Job changes.
- **Download policy** — mark any Playlist *Keep downloaded*, and its Bilibili
  Tracks download in the background, two at a time, and stay. Smart playlists
  pick their Tracks by rules on favorites, ratings, plays, text, and when a
  Track was added or played. An admin's storage limit makes room by removing the
  least favorite Downloads nothing keeps, never one downloaded, played, or kept
  within the last day, nor the only copy of a video gone from the site.
  `GET /api/storage` shows the space in use and previews another limit. See the
  [Download policy](docs/contributing/design-notes/Download%20policy.md) note.

### Changed

- Renamed the project from stream to medleyplay.
- A Library backend's `locate` answers *missing* for a file that is gone,
  instead of raising, so an unplugged drive can't fault its plugin.

### Removed

- **The 2019 prototype** — the Express server, the Create React App client, and
  the library-file builder are retired ahead of a rewrite. They remain in the git
  history.
