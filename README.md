# medleyplay

Play music on your local network, from your own files and from Bilibili.

> [!NOTE]
> **Status: rewrite in progress.** The 2019 prototype has been retired, and the
> new player is being designed. Nothing here is usable yet; see
> [`CHANGELOG.md`](CHANGELOG.md) for what has changed.

## Running the server

The server keeps its database in `MEDLEYPLAY_DATA_DIR`, by default
`~/Library/Application Support/medleyplay` on macOS.

```bash
uv run medleyplay serve                    # every interface, port 8000
uv run medleyplay reset-password <name>    # a lost password; signs the Account out
```

Open `http://<this machine>:8000/docs` to sign in and try the API. The first
Account, created through `POST /api/setup`, is the admin. Add a host name the
server should answer to, such as a router's DNS name, with
`MEDLEYPLAY_ALLOWED_HOSTS=music.home`.

## Development

Setup, the checks CI runs, and the pull-request checklist are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). Agents start at [`AGENTS.md`](AGENTS.md).

## Security

Please report vulnerabilities privately, as described in
[`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE)
