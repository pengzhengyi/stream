# Mode

> [!NOTE]
> **Status: being built (step 6b).** Deciding the Mode and reading the network
> are built; the settings, the API, and what waits while Offline are not yet.
> This note describes the Mode: whether medleyplay may contact music sites now,
> how *Auto* decides, and what waits while Offline. Why there is a Mode is in
> [Architecture](Architecture.md#online-and-offline); the
> Downloads it holds are in [Download policy](Download%20policy.md).

## Contents

- [Principles](#principles)
- [Auto](#auto)
- [What waits while Offline](#what-waits-while-offline)
- [Settings and the API](#settings-and-the-api)
- [The web client](#the-web-client)
- [Testing](#testing)
- [Left for later](#left-for-later)

## Principles

- **One Mode for the server:** the setting is *Auto*, the default, *Online*, or
  *Offline*. What it comes to now is Online or Offline, with the reason.
- **Offline, medleyplay contacts no music site.** Everything that would waits,
  and says what it waits for; nothing fails for being Offline.
- **Libraries and what is on disk are unaffected:** scanning, playing a Library
  Track or a Download, and preparing a zip member work in either Mode.
- **Going Offline is quick; coming back Online is careful.** A phone hotspot
  must stop Downloads at once, while a network that flickers shouldn't start
  them.

## Auto

<!-- cspell:ignore getinfo listnetworkserviceorder networksetup utun vmenet -->

Auto is Online when all of these hold, and Offline when any doesn't:

| Fact | Online when | How it is known |
| --- | --- | --- |
| A network | A physical network service has a router | `networksetup` |
| Not metered | No such network is one marked metered | Its router's address and subnet |
| The internet | A connectivity check reached it lately | See below |

- **A network is its physical service, not the default route.** A VPN puts the
  default route through a tunnel, which says nothing about the network under
  it. So the server reads `networksetup -listnetworkserviceorder`, and for each
  service in order, `networksetup -getinfo` for its router; the first service
  with a router is the network the server is on, and Wi-Fi or a cable is from
  its hardware port. Tunnels, bridges, and virtual interfaces (`utun`, `bridge`,
  `vmenet`, `docker`, `lo`) never count. Each command runs with `LC_ALL=C` and
  a short timeout, off the event loop.
- **A network is known by its router's hardware address and subnet.** macOS 15
  hides the Wi-Fi name from a process without Location access, and asking for
  that access from a server is out of place. The router's address comes from
  `arp -n`, after one `ping` to the router, which is on the local network, so
  the cache holds it after a wake or a join.
- **Marking a network metered** keeps the network the server is on now, with a
  name the admin gives, such as *iPhone hotspot*; the server reads which network
  that is, so the client never sends an address. A network on a phone hotspot's
  usual subnet (`172.20.10.0/28` for an iPhone, `192.168.43.0/24` for Android)
  is offered to be marked. A phone that changes its hotspot's address is a new
  network until marked again, which Settings says.
- **Not knowing fails safe:** when the network can't be read and the last one
  known was metered, Auto stays Offline until it can be read. With no network
  marked metered, not knowing the network changes nothing.
- **Reaching the internet** is a connectivity check: an HTTP request, with a
  5-second timeout and no redirects, that must answer exactly what the endpoint
  promises. The default is `http://captive.apple.com/hotspot-detect.html`,
  with `http://connect.rom.miui.com/generate_204` when Apple's can't be reached;
  both are in the config file. Neither is a music site, so the check touches no
  site's defenses. A redirect or another answer is a captive portal, which is
  unreachable.
- **When the check runs:** every five minutes while Online and quiet; every 30
  seconds after a failed check; at once when a Download fails for the network,
  as the plugin classifies it. A site's refusal, such as a block or a login, is
  never evidence of no internet. While the setting is Offline, nothing is
  checked.
- **Going Offline takes effect at once;** coming back Online waits until the
  facts have said Online for 30 seconds in a row, doubling after each flap up to
  two minutes and back to 30 seconds after five calm minutes. A flap is the
  facts turning Offline while settling, or within five minutes of going Online. The server starts
  Offline and waits the same way. A change of the setting takes effect at once.
- **Elsewhere than macOS,** the network facts are unknown, and Auto goes by the
  connectivity check alone.

## What waits while Offline

- **Nothing new contacts a music site.** A Job kind says whether it needs the
  network: a Download does, a scan and preparing a zip member don't. The
  runner's claim excludes network kinds while Offline, so a held Job stays
  queued, and its view says it waits for Online. Going Online starts them
  oldest first, no more at once than the runner allows.
- **Going Offline stops the network Jobs running,** and puts them back to wait,
  without counting an attempt or an interruption, since their process would
  otherwise keep contacting the site.
- **The download policy keeps deciding,** and its Downloads wait as Jobs, so the
  *Downloads* tab shows what will happen once Online. While Offline it removes
  cache copies but not Downloads, since a removed Download can't come back
  until Online.
- **A Track whose audio needs downloading is *available when online*:** its
  availability is `waiting_online`, a cause of its own, since the fix is to wait
  rather than to plug in a drive. Playing it starts its Download, which waits,
  and answers that rather than preparing.
- **Looking up and adding a link wait for Online:** the links service refuses
  them with the error code `offline`, answered as 409, so no other caller gets
  past it. Saving a link to add later comes with the add dialog in step 7, which
  doesn't ship without it.

## Settings and the API

- **The Mode has its own settings,** apart from the storage limit, so marking a
  network doesn't conflict with an edit of the limit: `GET` and `PUT
  /api/mode/settings` hold `setting` (`auto`, `online`, or `offline`) and the
  metered networks, at their own revision. `POST /api/mode/metered` marks the
  network the server is on now, with a name, and `DELETE
  /api/mode/metered/{id}` removes a mark. Changing them is for admins.
- **`GET /api/mode`** answers what the Mode is now, for any signed-in Account:

  ```json
  {
    "setting": "auto",
    "online": false,
    "reason": "metered",
    "network": { "kind": "wifi", "metered_as": "iPhone hotspot", "hotspot_like": true },
    "since": "2026-10-26T14:05:00Z",
    "checked_at": "2026-10-26T14:07:30Z",
    "online_at": null,
    "held_jobs": 3
  }
  ```

  `reason` is one of `set_online`, `set_offline`, `online`, `no_network`,
  `metered`, `unknown_network`, `unreachable`, and `settling`, an enum in the
  API. `kind` is `wifi`, `wired`, or `unknown`. `since` is when the Mode last
  changed, and `online_at`, while settling, when it goes Online if nothing
  changes.
- **The event stream sends a `mode` event,** the same body, when a stream opens
  and whenever the Mode changes, so a page that reconnects misses nothing.

## The web client

- **Offline shows in the header,** with the reason, such as *Offline: on a
  metered network*. Online shows nothing.
- **Settings gains a Network section:** the setting as three choices, the
  network the server is on, and, for an admin, *Mark this network metered*
  with a name, suggested for a hotspot's subnet, and the metered networks, each
  with a way to remove its mark. When the Mode is settling, it says when it goes Online.

## Testing

- **Deciding is a pure function** of the setting, the facts, the metered
  networks, and the times, so every row of the table above, the wait before
  Online, and its doubling are unit tests with a fake clock (29 and 31 seconds,
  a flap, five calm minutes), with a Hypothesis property: Auto is never Online
  on a metered network, with no network, or with an unknown network after a
  metered one.
- **The facts come through a probe** the tests replace; the macOS probe parses
  recorded command output, a VPN's and a hotspot's among them, and a test on
  macOS reads the real network, skipped in CI.
- **The runner** holds a network Job while Offline, stops one running when the
  Mode goes Offline without counting it, and starts held ones when Online, while
  a scan runs in either Mode.
- **Playback and links** answer Offline as above; the API and the event stream
  are tested through the app.

## Left for later

- **Saving a link to add once Online,** with the add dialog in step 7.
- **Metered networks found by the system,** such as macOS marking a hotspot as
  expensive, which needs Network.framework rather than a command.
- **IPv6-only networks,** whose router is found with `ndp` rather than `arp`;
  until then such a network is unknown.
- **Per-site reachability,** if more than one site arrives.
