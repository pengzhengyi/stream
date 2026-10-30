# Track details

> [!NOTE]
> **Status: proposed.** This note describes a Track's details (its title,
> artist, album, cover, and the rest), where each value comes from, how the
> household's own values win, and how medleyplay finds what a file doesn't say.
> Splitting a long file into songs is in [Segments](Segments.md).

## Contents

- [Why](#why)
- [The details](#the-details)
- [Origins and precedence](#origins-and-precedence)
- [The household's values](#the-households-values)
- [What medleyplay reads](#what-medleyplay-reads)
- [Covers](#covers)
- [Enrichers](#enrichers)
- [What the API shows](#what-the-api-shows)
- [Build order](#build-order)
- [Testing](#testing)
- [Left for later](#left-for-later)

## Why

A file saved from a video site often says nothing about its music: no tags, no
cover, only a name such as `BV1dm4y1s7ak.m4a`. Its details are in the video's
title and description, in a file the download tool can write beside it, or in
the household's head. medleyplay reads each, keeps where each value came from,
and lets the household's word win.

## The details

| Field | Kind | Example |
| --- | --- | --- |
| `title` | text | 過食性:アイドル症候群 |
| `artist` | text, as written | GUMI/MAYU |
| `album` | text | ケビョウニンゲン |
| `album_artist` | text | MAYU |
| `track_number`, `disc_number` | whole numbers from 1 | 3, 1 |
| `year` | a year | 2014 |
| `genre` | text | Vocaloid |
| `cover` | a cover's id; see [Covers](#covers) | `9f2c…` |

- **Text** is at most 512 characters, trimmed. The household's value outside these
  rules is refused; a value read from a file or a site is cut to fit instead, and
  blank text or a number out of range is no value.
- **The Track's row keeps the shown value** of each field, so sorting, search,
  smart playlists, and the Albums and Artists views read it as they do now.
- **A song list,** the songs inside a long file, is kept the same way; see
  [Segments](Segments.md).

## Origins and precedence

Each value is kept with its *origin*, so a later finding never overwrites the
household's word, and a source can be read again without losing anyone else's
values.

| Origin | What it is |
| --- | --- |
| `household` | A value someone in the household entered |
| `files` | The file's tags, and an image beside it with its name |
| `musicbrainz` | A release matched in MusicBrainz (later) |
| `video` | The video's own text: its title, uploader, description, and chapters, read from a file beside the audio, pasted by the household, or read from the site |
| `album_file` | For a song inside a long file, its album file's album fields; see [Segments](Segments.md) |
| `file_name` | The file's name, the title of last resort |

- **The shown value is the first origin that has one,** in the table's order.
  `files` comes before `video`, since tags are written on purpose, and when a
  file's tags are garbled, the household's value is the way out.
- **The album fields travel together:** `album`, `album_artist`, `year`,
  `track_number`, `disc_number`, and `cover` are shown from the first origin
  that names an album, so one Track never mixes two releases. A household value
  for any of them still wins on its own.
- **Empty text is a value:** the household can set a field to show nothing, and
  dropping its value shows the next origin's again.
- **A scan reads a file again** when it changed, or when the medleyplay that last
  read it read less from a file, so a field the tag reader learns fills in on the
  next scan.
- **Every value is a row** of `track_value`: the Track, the field, the origin,
  the value, and when it was recorded. One function writes values and rewrites
  the Track's shown values in the same transaction; the scan, adding a link,
  and the household all write through it, and nothing else writes the row.
- **Adding a site Track** records its title and artist as `video`, since they are
  the site's text, which the household may have tidied but needn't own.
- **The migration** records today's values: a Library Track's title as
  `file_name` when it is the file's name and as `files` otherwise, its other
  fields as `files`, and a site Track's as `video`.

## The household's values

- **Any signed-in Account may edit a Track's details,** as any may add a link:
  the catalog is the household's.
- ***Edit details*** shows each field's value, where it came from, and what each
  other origin says, so the household can take a found value with one click or
  type its own. Its boxes show what saving would show, as the album fields
  change together: naming an album of the household's own empties the file's
  track number at once. The client keeps its own copy of the shown-value rule
  for this; the server and the client are checked against one table of cases
  (`tests/support/shown_details.json`), so the two can't drift.
- **Saving sends only what changed,** each value set or dropped, so an edit of
  one field never overwrites another made meanwhile on another device. A value
  the household types or chooses that reads as what would show anyway, such as
  `03` over the file's track 3, is dropped rather than saved, so the found value
  still follows the file.
- ***Paste the video's details*** takes a video's title and description, copied
  from the site in a browser, and reads them as the `video` origin, as if the
  file beside the audio had held them. This works today, for any video, and
  asks the site nothing.
- **Many Tracks at once:** the same values, such as an album and its artist, can
  be set on several Tracks.

## What medleyplay reads

- **The file's tags,** as now, and its embedded cover.
- **The file's length:** a fragmented MP4, as Bilibili's downloads are, has no
  length in its header, and the tag reader answers none for about a third of
  them. The tags plugin reads it from the file's fragments instead.
- **Files beside the audio,** with its name: `<name>.info.json`, the video
  details yt-dlp writes with `--write-info-json`, and `<name>.jpg`, `.png`, or
  `.webp`, a cover such as `--write-thumbnail` writes. A scan notes them, and
  reads them again when they change.
- **The video id** comes from the Track's Bilibili Source, or from a file name
  that is a `BV` id, such as `BV1dm4y1s7ak.m4a`.
- **The video's text is read by one parser,** a pure function of the core: it
  drops bracketed tags such as `【MV】` or `[Hi-Res]`, splits `artist - title`
  and `title / artist`, recognizes an album by words such as `专辑`, `全专`, or
  `Full Album`, and reads a song list from the chapters or from timestamps in
  the description, such as `03:21 Song - Artist`.

## Covers

- **A cover is an image kept once** in `covers/` in the data folder, named by
  the SHA-256 of its bytes, so the songs of an album share one file.
- **Accepted:** JPEG, PNG, or WebP, known by their first bytes, not their names,
  at most 10 MiB.
- **Where covers come from:** the file's tags; an image beside the file with its
  name; the video's cover, through the file beside it; and the household's
  upload.
- **Served** with the type its bytes say, `nosniff`, and
  `Cache-Control: private, max-age=31536000, immutable`, since its name is its
  content.
- **The web client** shows covers in the table, the player, the queue, and the
  album view, and on the lock screen through the Media Session's artwork.
- **A cover no value names** is removed by the sweep at startup.

## Enrichers

An *enricher* proposes values from somewhere the scan doesn't look. It is a
plugin at a new extension point, `TRACK_ENRICHER`, so a buggy or slow one can't
harm the core, and each is turned on or off like any plugin.

- **It is asked** with the Track's shown values and their origins, its length,
  its file's name, and its video id if known. It answers values and a song
  list, and may write one cover into its working folder, which it names, as a
  download names its file.
- **The core checks an answer** like the household's input, records it under the
  enricher's origin, and replaces that origin's earlier values for the Track.
- **Each enricher runs in its own Job** per Track, so one waiting or failing
  doesn't hold another; the core queues them in order and gives each kind a
  limit of one at a time and a spacing between calls.
- **A segment is never enriched;** its album file is.
- **Queuing enrichment for many Tracks is for admins.**

| Enricher | Origin | Reads | When |
| --- | --- | --- | --- |
| `bilibili-details` | `video` | The video's details through yt-dlp, for a video with an id and no file beside it | Once yt-dlp reads Bilibili again |
| `musicbrainz` | `musicbrainz` | The MusicBrainz API and the Cover Art Archive, at most once a second | Later, if wanted |
| `ai` | suggestions only | A language model, with the household's key | Later, if wanted |

- **The site enricher is its own plugin,** not part of `bilibili`, so its faults
  never stop Downloads. The first refusal from the site stops all of it until an
  admin resets it, and it never asks the same video twice in a day.
- **An AI enricher would only suggest:** its values show in *Edit details* for
  the household to take, never as shown values, since it reads the same text
  the parser does.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/tracks/{id}/details` | Signed in | Every field's shown value and origin, and each origin's value |
| `PUT /api/tracks/{id}/details` | Signed in | The household's values for the Track, replacing its earlier ones |
| `POST /api/tracks/details` | Signed in | Sets the given household values on many Tracks |
| `POST /api/tracks/{id}/video-text` | Signed in | Reads a pasted title and description as the `video` origin |
| `GET /api/covers/{id}` | Signed in | A cover's image |
| `PUT /api/tracks/{id}/cover` | Signed in | The household's cover, as the request body |

Tracks in every list gain `cover`, `track_number`, `disc_number`, `year`, and
`genre`.

## Build order

1. **Lengths:** read a fragmented file's length from its fragments.
2. **Details and origins:** `track_value`, the one writer, the migration, and
   *Edit details*, with many Tracks at once.
3. **Covers,** with embedded and beside-the-file images.
4. **The video's text:** the parser, *Paste the video's details*, and
   `<name>.info.json` beside the file.
5. **Segments:** see [Segments](Segments.md).
6. **The site enricher,** once yt-dlp reads Bilibili again; then MusicBrainz and
   AI, if wanted.

## Testing

- **Precedence** as a Hypothesis property: the shown value is the first origin's
  in the order, the album fields come from one origin, dropping the household's
  value shows the next, and the Track's row always equals its shown values.
- **The parser** against a corpus of real-shaped titles and descriptions as
  multi-line literals: bracketed tags, `artist - title`, album words, and
  timestamp lists with and without hours, numbering, and artists.
- **Files beside the audio:** an `.info.json` read, changed, removed, and
  malformed, and a cover beside the file.
- **Lengths** against fragmented and plain MP4 files made with ffmpeg.
- **Covers:** each accepted type, a renamed file of another type, one over the
  limit, two Tracks sharing one cover, and the sweep.
- **Enrichers** through a test plugin; no test contacts a site, MusicBrainz, or a
  model.

## Left for later

- **MusicBrainz and AI enrichers.**
- **Covers in `medleyplay backup`,** which copies only the database.
- **A folder's `cover.jpg`** for every file in it.
- **Lyrics,** and naming songs by their audio with AcoustID.
