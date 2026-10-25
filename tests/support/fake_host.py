"""A scripted stand-in for a plugin host, for the ways a broken host can answer.

`python tests/support/fake_host.py MODE` loads nothing, reports the plugin
`parrot`, and then answers every call as MODE says:

- `invalid-reply`: a reply that isn't the operation's reply model;
- `garbage`: a line that isn't a message;
- `stale-reply`: a reply to another call first, then the right one;
- `reply-while-loading`: a reply before loading finishes.
"""

import json
import sys


def _send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main(mode: str) -> None:
    """Answer the server as `mode` says."""
    sys.stdin.readline()
    _send({"type": "loading", "name": "parrot"})
    if mode == "reply-while-loading":
        _send({"type": "reply", "id": 0, "peak_memory": 1})
    _send({"type": "loaded", "name": "parrot", "keys": {"echo": ["parrot"]}})
    _send({"type": "ready"})
    for line in sys.stdin:
        call_id = json.loads(line)["id"]
        match mode:
            case "invalid-reply":
                _send({"type": "reply", "id": call_id, "reply": {"words": 1}, "peak_memory": 1})
            case "garbage":
                sys.stdout.write("not a message\n")
                sys.stdout.flush()
            case _:
                _send(
                    {"type": "reply", "id": call_id - 1, "reply": {"text": "old"}, "peak_memory": 1}
                )
                _send({"type": "reply", "id": call_id, "reply": {"text": "new"}, "peak_memory": 1})


if __name__ == "__main__":
    main(sys.argv[1])
