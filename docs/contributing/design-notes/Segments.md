# Segments

> [!NOTE]
> **Status: in progress.** Splitting a file into songs, the songs API, and the
> server's side of playing a song (its stretch, availability, smart playlists,
> and the download policy) are built; the player, the editor, and the album view
> follow. This note
> describes splitting one long file, such as a whole album uploaded as one video,
> into its songs, and playing them as Tracks. Where a song list comes from is in
> [Track details](Track%20details.md).

## Contents

- [What a segment is](#what-a-segment-is)
- [Song lists](#song-lists)
- [Splitting a file](#splitting-a-file)
- [Playing a segment](#playing-a-segment)
- [The web client](#the-web-client)
- [What the API shows](#what-the-api-shows)
- [Testing](#testing)
- [Left for later](#left-for-later)

## What a segment is

- **A segment is one song inside a longer file:** a Track whose Source is a
  stretch of another Source's audio.

  ```text
  BV1dm4y1s7ak.m4a   2:28:46   the album file
    1  00:00  Intro              a segment
    2  03:12  Night Drive        a segment
    3  07:40  Blue Room          a segment
  ```

- **Its Source has the kind `segment`:** its locator is
  `<album file's Source id>/<segment id>`, and its details hold the start and
  end. So every Track still has a Source, and availability, playback, smart
  playlists, the policy, and removing a Library each look through the segment to
  the album file's Source. A segment Source has no file of its own; removing the
  album file's Source removes its segments, and their Tracks with them.
- **The file keeps its own Track,** the *album file*. Once split it is marked
  `split`: Songs, Artists, search, and smart playlists show its segments instead,
  while Albums still offers it, to play the file as one or to edit its songs.
- **A segment Track is a Track like any other:** its own favorite, rating,
  plays, place in Playlists and the queue, and details. Its length is its end
  less its start, and it was added when its album file was.
- **The file is never cut,** so splitting costs no disk.

Seeking far into these files is fast: a check in Chromium and WebKit seeks
5,000 seconds into a 2.5-hour fragmented `m4a` from Bilibili in under 0.7 s, and
both read its full length.

## Song lists

- **A song list is the songs' starts, in order,** each with a title and an
  optional artist; a song ends where the next starts, and the last at the end of
  the file.
- **It is checked:** starts rise strictly from 0 or later, every song is at
  least a second long and starts before the file ends, at most 300 songs, and
  titles and artists as for any Track.
- **Lists are found** in the video's chapters or description, read by the
  parser in [Track details](Track%20details.md#what-medleyplay-reads), and the
  household can paste one: one song a line, its time first or last, such as
  `00:00 Intro`, `1. 03:12 Night Drive - Blue Room`, or `Blue Room 1:07:40`.
- **A found list is a proposal.** It shows in the editor, and in the album view
  as *Split into N songs*; nothing is split until someone in the household says
  so.

## Splitting a file

- **Splitting is an act of the household,** from the editor, never a side
  effect of a scan or an enricher.
- **Each song keeps an id,** made when it is first added. Saving the editor's
  rows matches them by id: a song moved, renamed, or retimed stays the same
  Track, with its ratings, plays, and Playlist entries; a new row is a new Track;
  a row deleted removes its Track, with its favorites, ratings, and plays, so
  *Save* says how many songs it removes first.
- **A segment's details** default to its album file's album fields, through an
  `album_file` origin just above `file_name`, with its title and artist from its
  row and its track number from its place. The album is the file's album, or its
  title when it names none; the album artist is the file's album artist, or its
  artist; a song with no artist of its own is the album artist's. A change to the
  album file's details reaches its songs at once. The household can edit any of
  them.
- **A rescan that changes the file** keeps its songs, and the last song's length
  follows the file's. Each split remembers the file's length; once the length
  differs by a second or more, the songs are marked to check, and the album view
  says so.
- **A removed song's id is never reused,** so an editor left open can't give its
  ratings to a new song, and an album file's Source can't be removed while its
  songs remain.
- **Removing a Library** removes the songs split from its files, with their
  Tracks.
- **Unsplitting** removes every segment, after asking.

## Playing a segment

- **Asking to play a segment** answers as the album file would, with the
  segment's start and end.
- **The player moves on at the end** rather than on `ended`: a timer set from
  the position, checked again on each `timeupdate`, ends the song within a few
  milliseconds of its end.
- **The next segment of the same file plays on without a gap:** when the queue's
  next song starts where this one ends, the player only changes what is showing.
  Any other song in the same file, by *Next*, shuffle, or a click, is a seek
  within the loaded file, without loading it again.
- **The seek bar, the times, the saved position, and the lock screen** use the
  segment's own position and length, and seeking stays within it.
- **A play counts as for any Track,** by the segment's own length.
- **The lock screen** shows each song's title and cover; an album played with
  the iPhone locked is checked by hand before this is done, since a locked
  screen may slow the page's timers.

## The web client

- **Albums** shows a split file as an album of its songs, with *Play* and
  *Shuffle*, as for any album.
- ***Edit songs…*** on the album file's menu opens the editor: a row per song
  with its start, title, and artist; insert, delete, move, and retime; *Paste a
  list*; the lists found, to start from; and a click on a start to listen from
  there.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/tracks/{id}/songs` | Signed in | The album file's songs, with ids and ends, its length, whether to check them, and the lists found |
| `PUT /api/tracks/{id}/songs` | Signed in | The household's rows, by id; answers the segment Tracks |
| `DELETE /api/tracks/{id}/songs` | Signed in | Unsplits the file |
| `POST /api/tracks/{id}/playback` | Signed in | Now answers a segment's `start_ms` and `end_ms` |

Tracks in every list gain `segment_of`, the album file's id, and `split`.

## Testing

- **The list check and the parser** with a corpus of pasted lists, and a
  Hypothesis property that a list's segments tile the file without a gap or an
  overlap.
- **Saving rows:** a first split, a song inserted in the middle keeping every
  other song's ratings, a delete, a move, a retime, unsplitting, a rescan within
  and past a second, and removing the Library.
- **Through the segment's Source:** availability, playback, a smart playlist
  that matches songs but not their split album file, and the policy.
- **The player** in Vitest with a fake media element: ending at the end, playing
  on into the next segment without a reload, seeking within one, the saved
  position, and a play counted by the segment's length; and one Playwright run
  that plays across two segments of a real file.

## Left for later

- **Snapping starts to silence,** found with ffmpeg, near each start.
- **Exporting a split file** as separate files.
