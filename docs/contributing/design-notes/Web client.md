# Web client

> [!NOTE]
> **Status: implemented.** This note describes the client's views: the song
> table, Artists, Albums, Downloaded, Playlists, search, the keyboard
> shortcuts, and Settings, and how they get their data. What the client must do is in [MVP](MVP.md#client-notes);
> the player, the queue, and play modes are in
> [Playback](Playback.md#the-web-client).

## Contents

- [Data](#data)
- [Views](#views)
- [The song table](#the-song-table)
- [A song's menu](#a-songs-menu)
- [Keyboard shortcuts](#keyboard-shortcuts)
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
- **Favorites** is the smart playlist of favorite Tracks that the server keeps
  for every Account; see [Download policy](Download%20policy.md#smart-playlists).
  The client shows it once, first, with a heart, at `#/playlist?id=favorites`,
  and works out its Tracks from the hearts it already holds, newest added first
  as the server orders them, so a heart counts at once. The server doesn't
  record when a Track became a favorite, so *recently liked* waits for that.
- **Playlists gain songs from a song's menu;** renaming, reordering, and
  removing wait. See [A song's menu](#a-songs-menu).
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

## A song's menu

- **A "…" button holds a song's less frequent actions,** each an icon and
  words: *Play next* and *Add to queue*, *Go to artist* and *Go to album*, and
  *Add to playlist…*. Each song row has one, after its queue buttons, which a
  phone hides, since the menu holds them; the player has one beside the heart,
  without the queue actions.
- **Go to** opens the artist's view, or the album's under its album artist, as
  the Albums view groups it.
- **Radix's dropdown menu** draws it: unstyled, it handles the arrow keys, Home
  and End, typeahead, Escape returning focus to the button, and keeping the
  menu on screen, and it draws in a portal, so a table row doesn't clip it. It
  was chosen over Headless UI, Ariakit, React Aria, and writing one: it passed
  every keyboard check in the spike, is the most used, and is the smallest of
  the four. One module owns it, as with TanStack.
- **Add to playlist** is a native modal `<dialog>`: it lists the Account's own
  plain Playlists, those already holding the song checked and disabled, and one
  or several are chosen. Naming a new Playlist adds it, chosen, but it is made
  only when the song is added, so Cancel leaves nothing behind. Adding puts each
  chosen Playlist whole with the song at its end, keeping its *Keep downloaded*;
  the Playlists the server saves show at once, and the dialog says why if it
  refuses one. Escape, Cancel, or a click outside close it. A notice above the
  player says where the song went.

## Keyboard shortcuts

| Keys | Command |
| --- | --- |
| Space or K | Play or pause |
| ← and → | Back or ahead 5 seconds |
| Shift + ← and Shift + → | Previous and Next |
| - and = | Volume down and up, a mark at a time |
| M | Mute or unmute; changing the volume turns the sound back on |
| S, R, and L | Shuffle, Repeat, and favorite the song playing |
| / | Go to the search box |
| Q | Open or close *Up next*; where it is always open, go to it |
| Shift + / (?) | List the shortcuts |

- **Keys are physical keys,** as `KeyboardEvent.code` names them, so a shortcut
  sits in the same place on any keyboard layout; *?* is Shift and the */* key.
  A label names the key as the keyboard prints it, where the browser says
  (`navigator.keyboard.getLayoutMap()`, in Chromium), so the key a French
  keyboard prints *A* reads *A*; elsewhere, labels are a US keyboard's. A key
  held with Ctrl, Alt, or ⌘ is left to the browser unless a binding names that
  modifier.
- **A command has any number of keys,** none included, up to four.
- **The focused control keeps the keys it uses:** typing goes into a text box,
  an arrow moves a focused slider, and Space or Enter presses a button reached
  with the keyboard. A button focused by a click doesn't keep Space, so Space
  after clicking a song pauses it rather than playing it again. An open dialog
  or menu keeps every key.
- **Holding a key** repeats seeking and the volume, but not the others, so
  holding Space doesn't flicker between play and pause.
- **A screen reader's browse mode** takes bare letters and arrows for itself,
  so the shortcuts work in its focus mode, as on any page.
- **A control names its keys** in its hover text, such as *Play (Space or K)*,
  and in `aria-keyshortcuts`. The header's keyboard button, or *?*, lists them
  all, with a link to change them; a phone, which has no keyboard, hides the
  button.
- **Changing a shortcut** is in Settings: each key of a command has a remove
  button, and *Add keys* waits for the next press, modifiers included, and adds
  it, unless another command has it, which it names, waiting for other keys.
  Escape, or moving away, adds nothing, and *Reset to defaults* puts every
  command back. Keys the browser or the system keeps, such as ⌘ + W or F5, are
  refused too, since the page would never see them or would take them from the
  browser.
- **The shortcuts are the Account's,** so they follow it to any browser or
  device: `GET` and `PUT /api/me/preferences` hold the commands changed from
  the defaults, at the revision read, and a command left on its defaults takes
  a new default when the page gains one. The server keeps the keys without
  knowing the commands. The page shows this browser's copy of the Account's
  at once, then the server's, and reads them again when it is shown. A save
  that finds them saved elsewhere since reads the revision and saves again: the
  change chosen last wins. A saved command on keys another command has, as when
  a new command's default is keys already saved, goes back to its default; the
  rest stay as saved.
- **react-hotkeys-hook** listens for them: it matches physical keys with their
  modifiers and leaves out form fields, and the page decides which keys a
  focused control keeps. It was chosen over tinykeys, hotkeys-js, and writing
  the listener: it is the most used, has no dependencies, and is a hook, so a
  listener comes and goes with the page. One module owns it, with one listener
  for each command.

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
  list loads, and the search runs a moment after typing stops. The first search
  opens the results and later ones change them in place, so Back leaves the
  search in one step. The results show
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

- **Appearance:** the theme, the same choice as the header's switch; every
  switch on the page shows the one chosen.
- **Keyboard shortcuts:** each command's keys, and changing them; see
  [Keyboard shortcuts](#keyboard-shortcuts).
- **Network:** whether medleyplay is Online or Offline and why, the network the
  server is on, and how many downloads wait for Online, from the `mode` event
  and `GET /api/mode`; the setting and the metered networks, from `GET
  /api/mode/settings`. An admin chooses the setting, which saves at once, marks
  the network the server is on metered with a name, and removes a mark; a member
  sees them. See [Mode](Mode.md#the-web-client).
- **Downloads and storage:** what the Downloads, prepared copies, and Downloads
  under way use, against the limit or the free disk, and what kept Playlists
  want, from `GET /api/storage`; and the storage limit, from `GET` and `PUT
  /api/settings`. Sizes are in decimal units, as Finder shows them.
  - **An admin changes the limit:** no limit, or a size in GB. A moment after
    the size stops changing, the page asks `GET /api/storage?limit=` what that
    limit would remove, and says so before saving. Saving sends the revision
    read; if someone saved first, the page shows the settings as they are now.
  - **A member sees the limit** and what it holds, with nothing to change.
  - **The removal order** has one choice today, so it is said in a sentence
    rather than offered as a menu.
- **Later sections** come with their features: linked accounts, Libraries,
  Accounts, and plugins.

Each section folds under its heading, a button that says whether it is open;
which are folded is kept per browser. A bar of the section names stays under the header as the page scrolls:
choosing one opens that section, scrolls to it, and moves focus to its heading,
and its last button folds or opens them all.

## Layout

| Width | Navigation | Queue |
| --- | --- | --- |
| Wider than 64rem | A rail on the left | A panel on the right |
| 48rem to 64rem | Tabs under the header | A panel opened from the player |
| Up to 48rem | A tab bar along the bottom, below the player | A sheet opened from the player |

A touch screen, which can't point, shows a row's actions all the time. The
page sizes itself to the dynamic viewport (`dvh`) and keeps the player and the
tab bar clear of the iPhone's home indicator (`env(safe-area-inset-bottom)`).

## Testing

- **Pure functions** for grouping, search, and the Favorites list, with Vitest.
- **The song table** in Vitest with virtualization off, since jsdom has no
  layout; Playwright scrolls a large Library in Chromium and checks that the
  page holds only the rows on screen.
- **Playwright** for moving between views, Back and Forward, search, favorites,
  ratings, the keyboard shortcuts, and Settings, at phone, tablet, and laptop
  widths. Whether a click or the keyboard focused a button differs only in a
  browser, so Space after a click is checked there.

## Left for later

- **Searching Bilibili,** the add dialog, the stage view, and the *Downloads*
  tab of Jobs.
- **Editing Playlists** from the client: renaming, reordering, and removing.
- **Loading Tracks page by page,** if a Library outgrows loading whole, and
  answering an unchanged list with a 304.
- **Recently liked,** which needs the server to record when a Track became a
  favorite.
- **Sorting by a second column,** through a menu that works on touch.
