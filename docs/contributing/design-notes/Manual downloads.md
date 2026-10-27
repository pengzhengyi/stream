# Manual downloads

> [!NOTE]
> **Status: proposed (step 7).** This note describes how the household gets a
> site Track's audio when medleyplay can't: adding a Track whose video can't be
> read, seeing that its Download failed, and adding the file themselves. How
> medleyplay downloads on its own is in [Bilibili](Bilibili.md); what the web
> client shows around it is in [Web client](Web%20client.md).

## Contents

- [Principles](#principles)
- [Looking up a code or a link](#looking-up-a-code-or-a-link)
- [Adding a video that can't be read](#adding-a-video-that-cant-be-read)
- [A failed Download](#a-failed-download)
- [Adding the file](#adding-the-file)
- [Other ways to get it](#other-ways-to-get-it)
- [The web client](#the-web-client)
- [What the API shows](#what-the-api-shows)
- [Testing](#testing)
- [Left for later](#left-for-later)

## Principles

- **medleyplay always tries first.** Adding a Track starts its Download, as it
  does now; the household's own file is for when that fails, or for any time
  they would rather.
- **A file the household adds is a Download like any other,** a *manual
  Download*: it plays, joins the queue and the lock screen, works Offline, and
  shows in *Downloaded*. Nothing after it knows how it was made, except its
  backend, `manual`.
- **medleyplay never runs another tool.** The other ways it lists are for the
  household to run on their own computer; a refusal from the site is never
  answered by asking again some other way.
- **The file wins.** Adding a file cancels the Track's Download Job, and
  replaces a Download it already has.

## Looking up a code or a link

- **The lookup takes a code as well as a link:** a bare `BV` or `av` id, such as
  `BV1Xx41117Tz` or `av170001`, becomes `https://www.bilibili.com/video/<id>`
  before the allowlist sees it. Only that shape is turned into a link; any other
  text is still checked as a link.
- **The plugin canonicalizes it as it does a link,** so `av` ids still become
  `BV` ids.

## Adding a video that can't be read

- **A lookup whose read fails still answers,** with `readable: false` and why,
  instead of an error, whatever the failure: a fault, a network failure, a
  refusal, *gone*, or *needs a login*. It names the video and the part the link
  did, or part 1, and offers no qualities. A link that names no video is still
  refused with 422.
- **The failure is remembered** with the lookup's ten-minute memory, so the add
  that follows doesn't ask the site again.
- **Adding then trusts the household's details:** each part's number, title,
  and artist, checked as before for length, with at most 50 parts, and the
  quality *best*. The duration is unknown until a file comes.
- **Each part still gets a Track, a Source, and a Download Job,** so the
  downloader gets its try; a video the site says is *gone* gets one attempt, and
  its Source becomes *unavailable* as before.
- **Offline, looking up and adding are still refused,** since a short link must
  be followed and the read needs the site.

## A failed Download

- **A site Track's Download has failed** when it has no Download and the latest
  download Job of its Source failed: its three attempts ran out, or the
  household or the policy gave up on it. A new Job, from playing it again or
  from the policy, makes it *downloading* again.
- **The Track says so:** `download_failed` on the Track, beside `downloaded`,
  and the Track's download state with the failure's message from
  `GET /api/tracks/{id}/download`.
- **Nothing changes in how the Track plays:** playing a failed Track answers its
  failed Job, as it does now.

## Adding the file

- **`PUT /api/tracks/{id}/download?name=<file name>` takes the file as the
  request body,** not a form, so no multipart parser is needed. Any signed-in
  Account may add one, as any may add a link.
- **The Track's Source is its site Source,** the first if it has several; a
  Track without one answers 409.
- **The file is checked** before it is kept:
  - its name's extension is one the player serves: `m4a`, `mp4`, `mp3`, `flac`,
    `ogg`, `oga`, `opus`, `wav`, `aif`, `aifc`, or `aiff`;
  - it is at most 1 GiB, counted as it arrives, so a larger one stops with 413;
  - tinytag reads it as audio with a positive duration; otherwise 422.
- **It is written beside the Downloads,** under a temporary name, fsynced, then
  renamed over `downloads/<source id>.<ext>` in the transaction that records
  it. A crash before the commit leaves a file no Download names, which the sweep
  at startup removes.
- **The transaction** cancels the Source's active download Job, replaces any
  earlier Download and its file, and records the Download with the backend
  `manual`, no quality, its size, and the time. A Track without a duration takes
  the file's.
- **The policy never removes a manual Download,** since it couldn't come back
  by itself: it is not *replaceable*, as a Download whose Source is unavailable
  isn't. It still counts toward the storage limit.
- **Offline, a file can still be added:** nothing contacts the site.

## Other ways to get it

- **The web client keeps the list,** per Source kind, so the plugin API and the
  plugins don't change. Each way has a name, a line on when to try it, and a
  command with the part's link filled in, with a button to copy it.
- **For `bilibili`:** yt-dlp with a cookies file or the browser's cookies, yt-dlp
  with the extractor fix under review, BBDown, yutto, lux, and you-get, in the
  order the household found them to work.
- **The list shows** in the add dialog, folded, and in the dialog for adding
  the file.

## The web client

- **Search with *Bilibili* chosen** takes a link or a code. *Enter* looks it up
  and opens the add dialog; this is all *searching Bilibili* means for now.
- **The add dialog, when the video was read:** its title and uploader; each
  part with its suggested title and artist, editable, and a box to choose it;
  the quality; and *Add*.
- **When it couldn't be read:** why, then one part with its number, a title,
  and an artist to fill in, and *Add*; the household can add more parts.
- **After adding,** the dialog closes and says how many Tracks were added and
  that they are downloading.
- **A failed Track** shows *Download failed* where its availability shows, with
  *Add the file…*. The Track's menu has *Add the file yourself…* for any site
  Track, failed or not.
- **The add-the-file dialog:** the failure's message, the other ways, a file
  picker, and *Add*, with the upload's progress. When it finishes, the Track
  plays.

## What the API shows

| Route | Who | Does |
| --- | --- | --- |
| `POST /api/links/lookup` | Signed in | Now takes a code too, and answers `readable: false` with why when the read fails |
| `POST /api/links` | Signed in | Now adds parts of a video that couldn't be read, with the household's details |
| `GET /api/tracks/{id}/download` | Signed in | The Track's site Source: its link, whether it is downloaded, downloading, or failed, and the failure's message |
| `PUT /api/tracks/{id}/download` | Signed in | Adds the file in the body as the Track's Download; 413 too large, 422 not audio, 409 no site Source |

Tracks in every list gain `download_failed`.

## Testing

- **Through the test plugin `tube`,** scripted to fail: a lookup that can't
  read answers `readable: false` for each kind of failure, the add that follows
  doesn't read again, and adding with the household's details makes Tracks and
  Jobs.
- **Adding the file:** each accepted extension, a name with no extension or
  another one, an empty file, one over the limit, a file tinytag can't read, a
  Track without a site Source, a running Job cancelled, an earlier Download
  replaced, the duration filled in, and Offline.
- **The policy** keeps a manual Download over the limit and removes a
  downloaded one beside it.
- **The web client:** the code and link lookups, both add dialogs, the failed
  state, the other ways with the link filled in, and an upload, in Vitest and
  one Playwright run against a server with `tube`.

## Left for later

- **Finding a file in a folder** the household downloads into, matched by its
  video id, instead of uploading it.
- **Removing a manual Download** by hand.
- **Other ways for other sites,** when there are other sites.
