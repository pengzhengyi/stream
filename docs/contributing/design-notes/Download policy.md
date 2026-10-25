# Download policy

> [!NOTE]
> **Status: designed (step 6a); not built yet.** This note describes how
> medleyplay decides which Bilibili Tracks keep a Download on the server's disk:
> smart playlists and their rules, the *Keep downloaded* switch, the storage
> limit, and the pure `plan` that downloads what is wanted and removes what must
> go. What the policy must do is in [MVP](MVP.md#enforce-the-policy); why it is
> all in the core is in [Architecture](Architecture.md#policy). The Mode, which
> holds Downloads while Offline, is step 6b.

## Contents

- [Principles](#principles)
- [Smart playlists](#smart-playlists)
- [Rules](#rules)
- [The wanted set](#the-wanted-set)
- [Settings](#settings)
- [Storage use](#storage-use)
- [What may be removed](#what-may-be-removed)
- [Planning](#planning)
- [Removal order](#removal-order)
- [Applying a plan](#applying-a-plan)
- [Evaluating](#evaluating)
- [What the API shows](#what-the-api-shows)
- [Testing](#testing)
- [Left for later steps](#left-for-later-steps)

## Principles

Removal deletes the household's files, so the policy is built to fail closed:

- **Nothing is removed without a limit.** The default is no limit.
- **Nothing irreplaceable is removed:** a Download that can't be downloaded
  again stays, whatever the limit.
- **Nothing recent is removed:** a file downloaded, served, or wanted in the last
  day stays, so a rule typo or a lowered limit can be undone before it costs
  anything.
- **A removal makes room for a Download that starts,** or brings use back under
  a limit; it never happens for its own sake.
- **An evaluation that can't read its state removes nothing.**

## Smart playlists

- **A smart playlist is a Playlist with rules** in place of entries. The
  `playlist` table gains `rules`, JSON or null, and `keep_downloaded`, a
  boolean. A Playlist with rules has no entries; one without rules is the
  ordered list it is today.
- **`PUT /api/playlists/{id}`** takes `track_ids` for a plain Playlist, or
  `rules` for a smart one, never both, plus `keep_downloaded` for either. The id
  is still chosen by the client, so creating one stays retry-safe, and putting a
  smart playlist over a plain one, or back, replaces it whole.
- **Any Playlist can be *Keep downloaded*,** plain or smart. The MVP named the
  switch on smart playlists; a plain Playlist of songs for the car is the
  commonest wish, and to the policy both are a set of Tracks.
- **`GET /api/playlists/{id}`** of a smart playlist lists the Tracks its rules
  match now, newest added first, with how many there are and the estimated size
  of the ones without a Download, so the household sees what a switch would
  keep before turning it on.

## Rules

Rules are a typed, versioned schema. The domain holds them as plain dataclasses
and matches them; the application reads and writes their JSON with Pydantic, so
the domain stays free of frameworks.

```json
{
  "version": 1,
  "match": "all",
  "conditions": [
    { "field": "favorite", "op": "is", "value": true },
    { "field": "rating", "op": "at_least", "value": 4 },
    { "field": "artist", "op": "contains", "value": "周杰伦", "negate": true },
    { "field": "added", "op": "within_days", "value": 30 },
    { "field": "source_kind", "op": "is", "value": "bilibili" }
  ]
}
```

| Field | Operators | Value |
| --- | --- | --- |
| `favorite` | `is` | `true` or `false` |
| `rating` | `is`, `at_least`, `at_most`, `unrated` | 1–5 stars; none for `unrated` |
| `play_count` | `at_least`, `at_most` | 0 or more |
| `last_played` | `within_days` | 1–3650 days |
| `added` | `within_days` | 1–3650 days |
| `title`, `artist`, `album` | `contains`, `is` | 1–512 characters |
| `source_kind` | `is` | A Source kind, such as `bilibili` or `library` |

- **`match`** is `all` or `any`, over 1–20 conditions, one level deep.
- **`negate: true`** turns any condition into its opposite, such as *artist
  doesn't contain*, so no field needs its own negative operators.
- **A rule is the owner's view:** `favorite`, `rating`, `play_count`, and
  `last_played` are the owning Account's own.

| A Track the owner never touched | Reads as |
| --- | --- |
| `favorite` | `false` |
| `rating` | none: only `unrated` matches it, and no bound does |
| `play_count` | 0 |
| `last_played` | never: no `within_days` matches it |

- **Days are instants:** *within 7 days* is within 7 × 24 hours of now, its
  boundary included.
- **Text is compared normalized:** Unicode compatibility folding (NFKC), then
  case folding, on both sides, so full-width letters and decomposed accents
  match their plain forms. Simplified and Traditional Chinese are different
  text: 周杰伦 doesn't match 周杰倫. `artist` is the Track's artist string as
  stored; splitting several artists is later.
- **A Track's `source_kind`** matches when any of its Sources has that kind.
- **Rules are checked when saved;** an unknown field, operator, or version is a
  422 naming it.
- **A version newer than the server reads is never half-read.** A stored rule a
  server can't read, after a downgrade say, makes its Playlist *unreadable*: it
  shows no Tracks, and every evaluation [fails closed](#evaluating) until the
  rule is saved again. A later version brings a function that upgrades each
  older document on read.
- **Matching is a pure function** of the rules, one Track's facts as one Account
  sees them, and the time. It runs in Python over a snapshot of the catalog: a
  household's catalog is thousands of Tracks, and one function serves the
  playlist view, the policy, and the tests.

## The wanted set

- **A Track is *wanted by* an Account** when one of that Account's *Keep
  downloaded* Playlists holds it. The wanted set is every Track any Account
  wants.
- **Computed at each evaluation, not stored.** The MVP's `wanted_by` table would
  be a cache of the rules and Playlists that must be kept in step with every
  favorite, rating, play, and rule change; computing it can't go stale. What it
  would have shown, why a Download is kept, comes from the same computation in
  `GET /api/storage`.
- **Only Tracks with a site Source count.** The snapshot reads Tracks with a
  site Source, such as a Bilibili part, and the facts their rules need; a
  Track whose audio is only in Libraries is never the policy's concern.
- **A wanted Track needs a Download** when it has no Library Source in state
  *ok* and none of its site Sources has a Download. A Library's being offline
  doesn't count, so an unplugged drive doesn't start a burst of Downloads that
  turn unwanted when it returns.
- **One Download per Track:** when a Track has several site Sources, the policy
  downloads the one with the lowest id that it can download. Every Download of a
  wanted Track is wanted.

## Settings

- **A `setting` table** holds the household's settings as one JSON document,
  validated by a Pydantic `Settings` model with a version, so adding a setting
  needs no migration.
- **`storage_limit`** is the most bytes Downloads and cache copies may use, or
  none, the default.
- **`removal_order`** is `least_favorite`, the only order in the MVP.
- **A revision guards every change.** `GET /api/settings` returns the document
  with its revision; `PUT /api/settings`, for an admin, takes the whole document
  with the revision it was read at, and a stale one is a 409. So a forgotten tab
  can't lower the limit over a newer change.

## Storage use

- **What the limit counts:** each Download's size, each cache copy's size on
  disk, and the reservation of each download Job the policy or anyone else
  started. The database isn't counted.
- **A reservation** is the Job's estimated size: the Track's duration times the
  chosen quality's bitrate, plus a tenth; `best` counts as 192 kbps, and a Track
  of unknown duration counts as 16 MiB. A Job's reservation ends with the Job.
- **The disk is guarded too, with or without a limit:** a Download starts only
  while the data folder's disk keeps the larger of 2 GiB and 5% of the disk free
  beyond every reservation. The guard and the limit are both counted down
  candidate by candidate as a plan starts Downloads.

## What may be removed

A Download may be removed only when **all** of these hold:

- **It is unwanted:** no Account's *Keep downloaded* Playlist holds its Track.
- **It is replaceable:** its Source is *ok* and a plugin that is on downloads its
  site. A Download of a video since taken down, or of a site whose plugin is off,
  is the only copy there will be, so it stays.
- **It is at rest:** it wasn't downloaded, served, or wanted in the last 24
  hours. *Served* covers a device playing it, whose player asks for range after
  range; *wanted* gives a household a day to undo a rule or Playlist change.
- **No Job is active for its Source.**

A **cache copy** may be removed once its file wasn't written or served in the
last 24 hours; it is always replaceable from its Library.

## Planning

`plan(state) -> Plan` is a pure function in the domain. The state is a snapshot
read in one transaction: the wanted set and who wants each Track, every Download
with its size and when it was downloaded, last served, and last wanted, the cache
copies, the active and failed download Jobs, which sites a plugin downloads, the
valid linked accounts, the limit, the free space, and the time.

1. **Candidates** are the wanted Tracks that need a Download and that the policy
   can start now: a plugin that is on downloads the Source's site, the Source is
   *ok*, no Job is active for it, and its last failure, if any, is
   [due a retry](#retrying-a-failure). They are taken most favored first: the
   removal order reversed.
2. **Each candidate in turn** is started if, after removing what may be removed,
   its reservation fits under the limit and the disk guard. Room is made by
   removing cache copies, least recently used first, then removable Downloads in
   [removal order](#removal-order), only as much as this candidate needs. A
   candidate that can't fit even so is skipped, and the next, smaller one may
   still fit.
3. **Over the limit with nothing to start,** removable files are removed in the
   same order until use is back under the limit, as when an admin lowers it.
4. **At most two policy Downloads are active at once,** counting those already
   running or queued; the rest wait for the next evaluation, which a finishing
   Download requests. So a large Playlist never floods the queue, and a Track
   someone plays never waits behind hundreds.
5. **The plan reports what it couldn't do:** wanted Tracks waiting their turn,
   wanted Tracks that don't fit under the limit, ones blocked by the disk guard,
   ones whose last download failed, and ones no plugin can download.

- **Rules win:** a wanted Track takes the place of a Download nobody asked to
  keep. The MVP downloaded first and removed after; making room first is the
  same outcome without ever going over the limit.
- **A plan never removes without a limit,** and never removes what
  [may not be removed](#what-may-be-removed).
- **Idempotent:** applying a plan exactly as planned, then planning again,
  plans nothing more, which a Hypothesis property checks.

### Which login downloads

The Account with the lowest id that wants the Track and has a valid linked
account on the site, or else the lowest that wants it, with no login. That
Account is the Job's requester, so the runner lends its login and no other. The
quality is the one the Source was added at.

### Retrying a failure

- **A wanted Source whose last download failed** is retried by the policy a day
  after that failure, and again a day after each failure since, three times in
  all. Then it waits for the household to retry it, and `GET /api/storage` lists
  it as failing.
- **Saving a login again** makes every wanted Source that failed for want of one
  due at once, as does an admin resetting a faulted plugin.

## Removal order

**Least favorite**, the MVP's order, decides which removable Download goes
first:

1. Tracks that are no Account's favorite, before favorites.
2. Then by the best rating any Account gave, unrated first.
3. Then least recently played by anyone, never played first.
4. Then oldest added, and then by Source id, so the order is total.

## Applying a plan

- **Removals first, then Downloads,** so the room is there before a Job
  reserves it.
- **A removal is checked again where it happens.** In one transaction, the
  Download's row is deleted only if it still may be removed, judged from the
  rows as they are now, and its file is renamed to `downloads/.removed-<id>-<uuid>`;
  after the commit the renamed file is unlinked. A Job that completes later
  renames its own file over `<source id>.<ext>`, which no removal touches. A crash
  leaves either the row with no file, which plays by downloading again, or a
  renamed file no row names, which the sweep at startup removes.
- **A plan is acted on fresh or not at all.** When anything requested an
  evaluation after the snapshot was read, the plan's removals are dropped and
  the next evaluation plans again; its Downloads still start, since starting one
  is always safe.
- **A Download action** submits a download Job as adding does, through
  `DownloadService`, whose entry point for the policy takes the requesting
  Account and doesn't return a failed Job in place of a new one.
- **A cache removal** unlinks the copy; the next play prepares it again.
- **Last served** is a new `last_served_at` column on `download`, set when the
  audio route opens the Download, and written at most once a minute per
  Download. **Last wanted** is `last_wanted_at`, set for every wanted Download
  by each evaluation that applies.

## Evaluating

- **One evaluation at a time,** on a thread of its own, starting 5 seconds after
  the first request, so a burst of changes is one evaluation. A request while
  one runs marks the next as due.
- **Requests come from** a download Job finishing, a favorite, a rating, a play,
  a Playlist or its rules changing, a Track added, a Library scan finishing, a
  plugin turned on or reset, a login saved, an Account deleted, and the
  settings. Rules on time, such as *added within 30 days*, need one an hour,
  which also backs up any request missed.
- **At startup** the server evaluates once, after the sweeps.
- **It fails closed:** an error reading the snapshot, or a Playlist whose rules
  are unreadable, aborts the evaluation before it plans anything, and the error
  shows in `GET /api/storage`. An action that fails is logged; the others still
  apply.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `PUT /api/playlists/{id}` | The owner | Saves a plain or smart Playlist and its *Keep downloaded* switch |
| `GET /api/playlists/{id}` | The owner | A smart playlist's current Tracks, their count, and the size not yet downloaded |
| `GET /api/settings` | Signed in | The household's settings and their revision |
| `PUT /api/settings` | An admin | Replaces the settings at a revision, and evaluates |
| `GET /api/storage` | Signed in | Use by Downloads, cache copies, and reservations; the limit and the free space; the wanted size, in total and by Account; what the last evaluation couldn't do, and why; and its error, if it failed |
| `GET /api/storage?limit=<bytes>` | An admin | What a plan at that limit would remove and start, without doing it |

## Testing

- **`plan` by Hypothesis properties** over generated snapshots:
  - with no limit, nothing is removed;
  - nothing that [may not be removed](#what-may-be-removed) is removed:
    wanted, irreplaceable, at rest, or with an active Job;
  - every Download started is a candidate, no Source gets a second Job, and at
    most two policy Downloads are active after the plan;
  - the reservations started, and the use left, are within the limit and the
    disk guard, counted together;
  - the files removed are a prefix of the removable ones in order, cache copies
    first, and no more than the started Downloads and the limit needed;
  - applying a plan exactly, then planning again, plans nothing more;
  - applying it, completing its Downloads at sizes other than estimated, and
    planning until nothing changes, ends;
  - the plan doesn't depend on the order of the snapshot's rows;
  - raising the limit never removes more, and wanting one more Track never
    removes a wanted Download.
- **Rules:** each field, operator, and `negate` by example, with the table of
  untouched Tracks; rules round-trip through JSON; a newer version, an unknown
  field, and too many conditions are refused.
- **Applying:** a removal whose Download was served, wanted, or given a Job since
  the snapshot is skipped; a crash between the rename and the commit, and after
  it, both recover; a plan whose snapshot is stale removes nothing.
- **Through the services:** a *Keep downloaded* Playlist downloads its Tracks
  two at a time through the `tube` test plugin; lowering the limit removes
  removable Downloads, files and rows, and nothing else; a removed video's
  Download stays; a failed Job is retried a day later, and at once when the
  login is saved again; an unreadable rule stops every removal.

## Left for later steps

- **Smart playlists limited to N Tracks**, nested rules, rules on Playlists or
  Libraries, and splitting several artists.
- **A limit per Account**, and other removal orders.
- **The Mode**, which holds policy Downloads while Offline: step 6b.
- **The client views** for rules, the switch, storage, and the preview of a new
  limit: step 7.
