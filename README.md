# medleyplay

Play music on your local network, from your own files and from Bilibili.

> [!NOTE]
> **Status: rewrite in progress.** The 2019 prototype has been retired, and the
> new player is being designed. Nothing here is usable yet; see
> [`CHANGELOG.md`](CHANGELOG.md) for what has changed.

## Running the server

The server keeps its database and its config file, `medleyplay.toml`, in
`MEDLEYPLAY_DATA_DIR`, by default `~/Library/Application Support/medleyplay` on
macOS.

```bash
uv run medleyplay serve                    # every interface, port 8000
uv run medleyplay serve --safe-mode        # with every plugin off, for this run
uv run medleyplay reset-password <name>    # a lost password; signs the Account out
```

The server serves the web player, which you build once, and again after
changing it; it needs Node 24+:

```bash
cd web && npm ci && npm run build          # writes the player into the package
```

Open `http://<this machine>:8000/` on any device on the network. On a new
server, the first page creates the first Account, which is the admin. Each
device plays in its own browser, with its own queue, and the lock screen's
controls work through the Media Session API. Add a host name the server should
answer to, such as a router's DNS name, with
`MEDLEYPLAY_ALLOWED_HOSTS=music.home`.

To add music from Bilibili, turn its plugin on in `medleyplay.toml`, as below.
It is off by default because yt-dlp
can't read Bilibili until an upstream fix ships. Then save your Bilibili login
from an exported cookies file with `PUT /api/me/linked-accounts/bilibili`, and
add a video's parts with `POST /api/links/lookup` and `POST /api/links`; each
part downloads in the background and plays like any other song. The login stays
in the macOS Keychain.

Until the Libraries view arrives, register a folder or a zip archive of your
music through the API at `http://<this machine>:8000/docs` with
`POST /api/libraries`, such as
`{"name": "Music", "kind": "folder", "path": "~/Music"}`; its scan shows in
`GET /api/jobs`, and its songs in the player. A song compressed in a zip archive
is copied once into the cache in the data folder, and shows *Preparing* until
then.

To keep songs on this machine, turn a Playlist's `keep_downloaded` on with
`PUT /api/playlists/{id}`; its Bilibili songs download in the background and
stay. A smart playlist's `rules`, such as *favorites added in the last 30
days*, choose its songs as they change. An admin can cap the space downloads use
with `PUT /api/settings`; the least favorite downloads no Playlist keeps then make
room, but never one played or kept in the last day. `GET /api/storage` shows the
space in use, and `GET /api/storage?limit=<bytes>` what a new cap would remove.

The config file is optional; a missing setting takes its default, and a change
applies on restart. This one lets the admin add Accounts beyond the first,
turns the `bilibili` plugin on, and turns the tag reader off:

```toml
multiple_accounts = true

[plugins.bilibili]
enabled = true

[plugins.tinytag-tags]
enabled = false
```

`[[mode.checks]]` tables, each a `url`, a `status`, and an optional `body`,
replace the connectivity checks *Auto* uses to tell whether the internet can be
reached; see the [Mode](docs/contributing/design-notes/Mode.md#auto) note.

> [!TIP]
> When the macOS firewall is on, other devices can't connect until Python is
> allowed incoming connections: accept the prompt on first start, or add it in
> System Settings › Network › Firewall › Options.

## Development

Setup, the checks CI runs, and the pull-request checklist are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). Agents start at [`AGENTS.md`](AGENTS.md).

## Security

Please report vulnerabilities privately, as described in
[`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE)
