# Track details

> [!NOTE]
> **Status: proposed.** This note describes a Track's details (its title,
> artist, album, cover, and the rest), where each value comes from, how the
> household's own values win, and how *enrichers* find what a file doesn't say.
> Splitting a long file into songs is in [Segments](Segments.md).

## Contents

- [Why](#why)
- [The details](#the-details)
- [Origins and precedence](#origins-and-precedence)
- [The household's own values](#the-households-own-values)
- [Covers](#covers)
- [Enrichers](#enrichers)
- [When enrichment runs](#when-enrichment-runs)
- [What the API shows](#what-the-api-shows)
- [Build order](#build-order)
- [Testing](#testing)
- [Left for later](#left-for-later)

## Why

A file downloaded from a video site often says nothing about its music: no tags,
no cover, only a name such as `BV1dm4y1s7ak.m4a`. Its details are elsewhere: in
the video's title and description, in a music database, or in the household's
head. medleyplay gathers them from each place, keeps where each came from, and
lets the household's word win.

## The details

| Field | Kind | Example |
| --- | --- | --- |
| `title` | text | 過食性:アイドル症候群 |
| `artist` | text, artists joined with ` / ` | GUMI / MAYU |
| `album` | text | ケビョウニンゲン |
| `album_artist` | text | MAYU |
| `track_number`, `disc_number` | whole numbers from 1 | 3, 1 |
| `year` | a year | 2014 |
| `genre` | text | Vocaloid |
| `cover` | a cover's id, see [Covers](#covers) | `9f2c…` |
| `track_list` | songs in a long file, see [Segments](Segments.md) | `00:00 Intro`, … |

Text is at most 512 characters, trimmed. The Track's row keeps the value shown
for each field, so sorting, search, smart playlists, and the Albums and Artists
views read it as they do now.

## Origins and precedence

Each value is kept with its *origin*, so a later finding never overwrites the
household's word, and an enricher can be run again without losing anyone else's
values.

| Origin | What it is |
| --- | --- |
| `you` | A value the household entered |
| `files` | The file's tags, and covers beside it in its folder |
| `musicbrainz` | A release matched in MusicBrainz, with its cover from the Cover Art Archive |
| `ai` | A reading of the site's details by a language model, when the household turns it on |
| `site` | The video's own details on the site: its title, uploader, description, chapters, and cover |
| `file name` | The file's name, the title of last resort |

- **The shown value is the first origin that has one,** in the table's order,
  for every field but the track list, whose order is `you`, `site`, `ai`,
  `musicbrainz`: the uploader's timestamps fit the file exactly, while a
  database's track lengths drift over a mix's gaps.
- **Every value is a row** of `track_detail`: the Track, the field, the origin,
  the value, and when it was recorded. Writing any of a Track's values rewrites
  its shown values in the same transaction.
- **A scan writes `files` and `file name`,** not the Track's row directly. Adding
  a site Track writes the household's chosen title and artist as `you`.
- **The migration keeps today's values:** a Library Track's as `files`, a site
  Track's as `you`.

## The household's own values

- **Any signed-in Account may edit a Track's details,** as any may add a link:
  the catalog is the household's.
- **`PATCH /api/tracks/{id}/details`** sets `you` values; a field set to `null`
  drops the household's value, and the next origin shows again.
- **`PATCH /api/tracks/details`** sets the same values on many Tracks at once,
  such as the album and its artist on every song of a split file.
- **The web client's *Edit details*** shows each field's value and, beside it,
  where it came from and what else was found, so the household can take a found
  value with one click or type its own.

## Covers

- **A cover is an image kept once** in `covers/` in the data folder, named by
  the SHA-256 of its bytes, so the songs of an album share one file.
- **Accepted:** JPEG, PNG, or WebP, known by their first bytes, not their names,
  at most 10 MiB.
- **Where covers come from:** an image in the file's tags; an image beside the
  file named like it (`BV1dm4y1s7ak.jpg`) or `cover` or `folder`; the video's
  cover; the Cover Art Archive; and the household's upload.
- **`GET /api/covers/{id}`** serves one, cached for a year since its name is
  its content. **`PUT /api/tracks/{id}/cover`** takes an image as the request
  body, as the household's.
- **The web client** shows a Track's cover in the player, the queue, the album
  view, and on the lock screen through the Media Session.
- **A cover no value names** is removed by the sweep at startup.

## Enrichers

An *enricher* reads what the catalog knows about a Track and proposes values. It
is a plugin at a new extension point, `TRACK_ENRICHER`, so a buggy or slow one
can't harm the core, and each is turned on or off like any plugin.

- **It is asked** with the Track's shown values and their origins, its
  duration, its file's name, the site video id if one is known, and the
  contents of a video-details file beside it, if any. It answers values for
  the fields it found, a track list, and at most one cover's bytes.
- **The core checks every answer** like the household's input, records it under
  the enricher's origin, and replaces that origin's earlier values for the
  Track; a field it no longer finds is dropped.
- **Enrichers run in order,** `site`, then `musicbrainz`, then `ai`, each seeing
  what the ones before found.

| Enricher | Origin | On by default | Reads | Network |
| --- | --- | --- | --- | --- |
| `bilibili` | `site` | yes | A `<file name>.info.json` beside the file, as yt-dlp writes it; otherwise the video's details through yt-dlp, when it can read the site | Only without the file |
| `musicbrainz` | `musicbrainz` | yes | The MusicBrainz API, at most once a second, and the Cover Art Archive | Yes |
| `ai` | `ai` | no | A language model through the Anthropic API, with the household's key | Yes |

- **The site enricher parses the video's text:** it drops bracketed tags such as
  `【MV】`, splits `artist - title`, recognizes an album video by words such as
  `专辑`, `全专`, or `Full Album`, and reads a track list from the video's
  chapters or from timestamps in its description, such as `03:21 Song - Artist`.
  The parser is a pure function of the core, shared with the track-list editor.
- **The MusicBrainz enricher** searches by the artist and album found so far,
  and takes a release only when the search scores it 90 or more and its track
  count and length agree with the file; otherwise it answers nothing.
- **The AI enricher** sends the site's text and what was found, never audio, and
  asks for the fields and a track list in a fixed JSON schema. It is off until
  the household turns it on in Settings and saves a key, which is kept in the
  Keychain. Settings says what it sends.
- **An enricher that contacts the network runs in a Job** that waits while
  Offline, as a Download does. The site enricher follows every Bilibili rule:
  one video at a time, and a refusal is a fault, never asked again another way.

## When enrichment runs

- **After a scan** adds a Track or changes its file, and **after adding** a site
  Track: one `enrich_track` Job per Track, target `track:<id>`, at most one
  active per Track.
- **On request:** *Find details* on a Track or an album, and *Find details for
  every Track* in Settings, which queues the Tracks that lack a title other than
  their file name, an artist, or a cover.
- **Jobs run one at a time,** so a scan of a thousand files doesn't burst
  requests at any site.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/tracks/{id}/details` | Signed in | Every field's shown value and origin, with each origin's value |
| `PATCH /api/tracks/{id}/details` | Signed in | Sets or drops the household's values |
| `PATCH /api/tracks/details` | Signed in | The same values on many Tracks |
| `POST /api/tracks/enrich` | Signed in | Queues enrichment for the given Tracks, or for every Track lacking details |
| `GET /api/covers/{id}` | Signed in | A cover's image |
| `PUT /api/tracks/{id}/cover` | Signed in | The household's cover for a Track |

Tracks in every list gain `cover`, `track_number`, `disc_number`, `year`, and
`genre`.

## Build order

1. **Details and origins:** the `track_detail` table, shown values, the scan
   writing `files`, the household's values, covers, and *Edit details*.
2. **Segments:** see [Segments](Segments.md).
3. **Enrichment:** the extension point, the Jobs, the site enricher and its
   parser, and *Find details*.
4. **MusicBrainz** and the Cover Art Archive.
5. **AI,** off by default.

## Testing

- **Precedence** as a Hypothesis property: for any set of origins' values, the
  shown value is the first origin's in the order, and dropping the household's
  value shows the next.
- **The parser** against a corpus of real-shaped titles and descriptions as
  multi-line literals: bracketed tags, `artist - title`, album words, and
  timestamp lists with and without hours, numbering, and artists.
- **Enrichers** through a test plugin with scripted answers, and the real ones
  against recorded responses; no test contacts a site, MusicBrainz, or the
  Anthropic API.
- **Covers:** each accepted type, a renamed file of another type, one over the
  limit, two Tracks sharing one cover, and the sweep.

## Left for later

- **Lyrics.**
- **Fingerprinting audio** with AcoustID to name songs no text names.
- **Several artists as a list** rather than one joined text.
