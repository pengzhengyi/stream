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

Open `http://<this machine>:8000/docs` to sign in and try the API. The first
Account, created through `POST /api/setup`, is the admin. Add a host name the
server should answer to, such as a router's DNS name, with
`MEDLEYPLAY_ALLOWED_HOSTS=music.home`.

The config file is optional; a missing setting takes its default, and a change
applies on restart. This one lets the admin add Accounts beyond the first, and
turns one plugin off:

```toml
multiple_accounts = true

[plugins.bilibili]
enabled = false
```

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
