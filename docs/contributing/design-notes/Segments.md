# Segments

> [!NOTE]
> **Status: proposed.** This note describes splitting one long file, such as a
> whole album uploaded as one video, into its songs, and playing them as Tracks.
> Where a track list comes from is in [Track details](Track%20details.md).

## Contents

- [What a segment is](#what-a-segment-is)
- [Track lists](#track-lists)
- [Splitting a file](#splitting-a-file)
- [Playing a segment](#playing-a-segment)
- [The web client](#the-web-client)
- [What the API shows](#what-the-api-shows)
- [Testing](#testing)
- [Left for later](#left-for-later)

## What a segment is

- **A segment is one song inside a longer file:** a Track that plays part of
  another Track's audio, from a start to an end.

  ```text
  BV1dm4y1s7ak.m4a   2:28:46   the album file
    1  00:00  Intro              segment Track
    2  03:12  Night Drive        segment Track
    3  07:40  Blue Room          segment Track
  ```

- **The file keeps its own Track,** the *album file*. Once split, lists show its
  segments in its place; the album view still offers it, to play the file as one
  or to edit its track list.
- **A segment Track is a Track like any other:** its own favorite, rating,
  plays, place in Playlists and the queue, and details.
- **The file is never cut.** A segment plays from the album file's audio, so
  splitting costs no disk and changing a list is instant.

## Track lists

- **A track list is the songs' starts, in order,** each with a title and an
  optional artist; a song ends where the next starts, and the last at the end of
  the file.
- **It is checked:** starts rise strictly from 0 or later, every song is at
  least a second long and starts before the file ends, at most 300 songs, and
  titles and artists as for any Track.
- **Lists come from** the household, the video's chapters or the timestamps in
  its description, the AI enricher, and a matched MusicBrainz release, whose
  track lengths are added up only when they total within 2% of the file. Their
  order is in [Origins and precedence](Track%20details.md#origins-and-precedence).
- **One parser reads a pasted list** as the site enricher reads a description:
  one song a line, a time first or last, such as `00:00 Intro`,
  `1. 03:12 Night Drive - Blue Room`, or `Blue Room 1:07:40`.

## Splitting a file

- **The shown track list decides the segments.** A file without one is a single
  Track, as now.
- **Applying a list keeps Tracks by position:** the first song stays the same
  Track, with its ratings, plays, and Playlist entries, whatever its new title.
  New positions get new Tracks; Tracks past the new list's end are removed, with
  their favorites, ratings, and plays, so the editor asks first.
- **A segment's details** default to the album file's: its album, album artist,
  year, genre, and cover, with its title and artist from the list and its track
  number from its position. The household can still edit any of them.
- **A segment's availability is its album file's.**
- **A rescan that changes the file** keeps its track list when the length
  changed by less than a second; otherwise the list is kept but marked to check,
  and the album view says so.
- **The policy sees the album file only:** a segment has no Source and nothing
  to download.

## Playing a segment

- **Asking to play a segment** answers as the album file would, with the
  segment's start and end added.
- **The player** loads the file, seeks to the start, and moves on at the end.
  When the next song in the queue is the next segment of the same file, it plays
  on without reloading, so an album plays without a gap.
- **The seek bar, the times, and the lock screen** show the segment's own
  position and length, and seeking stays within it.
- **A play is recorded for the segment,** as for any Track.

## The web client

- **Albums** shows a split file as an album of its songs, with *Play* and
  *Shuffle*, as for any album.
- ***Edit track list…*** on the album file's menu opens the editor: a row per
  song with its start, title, and artist; *Paste a list*; the lists the
  enrichers found, to start from; and a click on a start to listen from there.
  *Save* says how many songs it adds or removes first.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/tracks/{id}/track-list` | Signed in | The album file's shown list, its origin, and the other origins' lists |
| `PUT /api/tracks/{id}/track-list` | Signed in | Sets the household's list, applies it, and answers the segment Tracks; an empty list drops the household's |
| `POST /api/tracks/{id}/playback` | Signed in | Now answers a segment's `start_ms` and `end_ms` |

Tracks in every list gain `segment_of`, the album file's id, and the album file
gains `segments`, its count.

## Testing

- **The list check and the parser** with a corpus of pasted lists, and a
  Hypothesis property that a list's segments tile the file without gaps or
  overlaps.
- **Applying a list:** a first split, a longer list, a shorter one that removes
  Tracks, renamed songs keeping their ratings, and a rescan within and past a
  second.
- **Playing:** the playback answer, and in the web client a queue of segments
  playing on without reloading, the seek bar within a segment, and a play
  recorded per segment.

## Left for later

- **Snapping starts to silence,** found with ffmpeg, near each start.
- **Exporting a split file** as separate files.
- **Naming songs by their audio** with AcoustID.
