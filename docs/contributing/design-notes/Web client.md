# Web client

> [!NOTE]
> **Status: in progress; the song table, favorites, and ratings are built, and
> the views, search, and Settings are next.** This note describes the client's views: the song
> table, Artists, Albums, Downloaded, Playlists, search, and Settings, and how
> they get their data. What the client must do is in [MVP](MVP.md#client-notes);
> the player, the queue, and play modes are in
> [Playback](Playback.md#the-web-client).

## Contents

- [Data](#data)
- [Views](#views)
- [The song table](#the-song-table)
- [Search](#search)
- [Favorites and ratings](#favorites-and-ratings)
- [Settings](#settings)
- [Layout](#layout)
- [Testing](#testing)
- [Left for later](#left-for-later)

## Data

- **The client loads the whole Library once:** `GET /api/tracks` and
  `GET /api/playlists` when the page opens, keyed by id. Every view, sort, and
  search is worked out in the browser from that data, with pure functions, so
  moving between views asks the server nothing. Until the first answer, the
  page says it is loading.
- **A change the client makes shows at once.** Setting a favorite or a rating
  changes that field of that Track, then sends the absolute value. Each write
  has a number, and only the answer to a field's latest write counts, so quick
  toggles can't settle out of order; the answer changes only the field it was
  about. A refused write puts back the last value the server confirmed, and
  says why. A fresh list from the server keeps any write still under way.
- **The client asks for the Tracks again** when a page that was hidden is shown
  again, when the event stream reconnects, and once a scan or a Download Job
  finishes, a second after the last such event. So a favorite set on another
  device, or a Download the storage limit removed, shows on coming back to the
  page.
- **The server adds one field, `downloaded`,** to each Track: whether a Source
  of the Track has a Download row, so a cache copy of a zip member doesn't
  count. Nothing else in the client's data can tell, and the catalog already
  finds it to work out availability. The client also reads `album_artist`,
  `added_at`, and `last_played_at`, which the API already has.
- **Large Libraries:** the Track list is loaded whole and the table draws only
  the rows on screen, so tens of thousands of Tracks scroll smoothly. Loading
  page by page from the server would make every view and search a server query;
  it waits until a Library is too large to load whole.

## Views

Each view is a hash route, so Back, Forward, and a bookmark work, and a reload
keeps the view. The routes are a few lines of our own over `hashchange`, with
no router package.

| View | Route | Shows |
| --- | --- | --- |
| Songs | `#/songs` | Every Track, in the song table |
| Artists | `#/artists` | Each artist, with how many Tracks and how long; one opens its Tracks |
| Albums | `#/albums` | Each album, under its album artist, or its artist when that is blank |
| Downloaded | `#/downloaded` | The Tracks with `downloaded`, in the song table |
| Playlists | `#/playlists` | *Favorites* first, then the Account's Playlists |
| Search | `#/search?q=…` | What the search found |
| Settings | `#/settings` | See [Settings](#settings) |

- **An artist's or album's Tracks** open at `#/artist?name=…` and
  `#/album?artist=…&name=…`, in the song table, so a name with a `/` is safe.
- **Artists are the artist field as written:** `初音ミク/米津玄師` is an artist
  of its own, since splitting names on a separator guesses wrong as often as
  right. Names that differ only in case or width are one artist. A blank artist
  or album is listed as *Unknown artist* or *Unknown album*.
- **Favorites** is a Playlist the client makes from the favorite Tracks, in the
  song table's order: it is always there, can't be renamed or deleted, and needs
  nothing new from the server. The server doesn't record when a Track became a
  favorite, so *recently liked* waits for that.
- **Playlists are read-only for now:** they list and play.
- **Playing from a view** queues the Tracks the view shows, in their order at
  the click; a later sort or a fresh list doesn't change the queue. A Track that
  can't play stays in the queue, and *Next* skips it.

## The song table

- **TanStack Table 9 with TanStack Virtual,** headless, so the page keeps its
  own look and real `<table>` semantics. Only the Tracks on screen are in the
  page; the rows above and below are spacer rows hidden from screen readers,
  and the table states `aria-rowcount`, the Tracks and the header row, with
  `aria-rowindex` on each row, so a screen reader counts every Track.
- **Columns:** favorite, title, artist, album, time, rating, plays, and added.
  Each sorts by a button in its header, which states `aria-sort`: a click sorts
  it, again the other way, and a third time returns to the server's order, the
  oldest added first. One column sorts at a time, since a second sort key would
  need a modifier key a touch screen lacks. Text sorts as people read it, by
  locale, with numbers in order and case ignored; time, rating, plays, and added
  sort as numbers and dates, smallest first.
- **Columns can be hidden and resized,** from a menu in the header row; the
  choice is kept per browser, versioned, and ignored when it can't be read.
- **One table module owns TanStack's types,** so the rest of the client sees
  Tracks and callbacks only.

## Search

<!-- cspell:ignore ｍｅｌｔ -->

- **One search box in the header,** with a scope toggle: *Library* or
  *Bilibili*. Library is built now; Bilibili shows only while the `bilibili`
  plugin is on, and can't be chosen until searching Bilibili exists, which is
  not in the MVP.
- **Library search** matches the words typed, each anywhere in a Track's title,
  artist, or album, ignoring case, width, and hiragana or katakana: NFKC, lower
  case, and katakana shifted to hiragana, so `ｍｅｌｔ` finds *Melt* and
  `くじら` finds *クジラ*. Each Track's folded text is worked out once, when the
  list loads, and the search runs a moment after typing stops. The results show
  the matching Tracks in the song table, and the artists and albums whose names
  match.

## Favorites and ratings

- **A heart** marks a favorite, in a row and in the player.
- **Five stars** rate a Track in its row; choosing the rating already given
  clears it. A phone, which has no room for the rating column, rates from the
  player.
- Both use `PUT /api/tracks/{id}/favorite` and `PUT /api/tracks/{id}/rating`,
  which take an absolute value, so a retry is harmless.

## Settings

One view, in sections, each saved on its own:

- **Appearance:** the theme, as in the header.
- **Downloads and storage:** the storage limit, the removal order, and what
  is used, from `GET` and `PUT /api/settings` and `GET /api/storage`, with a
  preview of what a lower limit would remove. Admin only, as the server
  requires.
- **Later sections** come with their features: Mode, linked accounts,
  Libraries, Accounts, and plugins.

## Layout

| Width | Navigation | Queue |
| --- | --- | --- |
| Wider than 64rem | A rail on the left | A panel on the right |
| 48rem to 64rem | Tabs under the header | A panel opened from the player |
| Up to 48rem | A tab bar along the bottom, above the player | A sheet opened from the player |

A touch screen, which can't point, shows a row's actions all the time. The
page sizes itself to the dynamic viewport (`dvh`) and keeps the player and the
tab bar clear of the iPhone's home indicator (`env(safe-area-inset-bottom)`).

## Testing

- **Pure functions** for grouping, search, and the Favorites list, with Vitest.
- **The song table** in Vitest with virtualization off, since jsdom has no
  layout; Playwright scrolls a large Library in Chromium and checks that the
  page holds only the rows on screen.
- **Playwright** for moving between views, Back and Forward, search, favorites,
  ratings, and Settings, at phone, tablet, and laptop widths.

## Left for later

- **Searching Bilibili,** the add dialog, the stage view, and the *Downloads*
  tab of Jobs.
- **Editing Playlists** from the client: creating, renaming, and adding Tracks.
- **Loading Tracks page by page,** if a Library outgrows loading whole, and
  answering an unchanged list with a 304.
- **Recently liked,** which needs the server to record when a Track became a
  favorite.
- **Sorting by a second column,** through a menu that works on touch.
