/**
 * @file The signed-in page: the views, the search, the queue, and the player.
 */

import { KeyboardIcon, SignOutIcon, WaveformIcon } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import { type Account, type Track, api } from "../api";
import { useLibrary } from "../library/useLibrary";
import { current, repeatAfter } from "../player/queue";
import { usePlayer } from "../player/usePlayer";
import { stepVolume } from "../player/volume";
import { hrefOf, useRoute } from "../routes";
import { hintOf, useBindings } from "../shortcuts";
import { AddToPlaylist } from "./AddToPlaylist";
import { Nav } from "./Nav";
import { PlayerBar } from "./PlayerBar";
import { QueuePanel } from "./QueuePanel";
import { SearchBox } from "./SearchBox";
import { ShortcutList } from "./ShortcutList";
import { type ShortcutHandlers, Shortcuts } from "./Shortcuts";
import { REPEATS, shuffleSaid } from "./playModes";
import { ThemeSwitch } from "./ThemeSwitch";
import type { TrackActions } from "./TrackTable";
import { CurrentView } from "./Views";

/** How long a notice, such as a song added to a Playlist, stays. */
const NOTICE_MS = 4000;
/** How far a shortcut seeks back or ahead, as the arrows do on the position. */
const SEEK_SECONDS = 5;
/** Where the queue can close, as the page's styles have it; wider, it is always open. */
const NARROW = "(width <= 64rem)";
const listFormat = new Intl.ListFormat(undefined, { type: "conjunction" });

/** Everything a signed-in Account sees. */
export function Library({
  account,
  onSignedOut,
}: {
  readonly account: Account;
  readonly onSignedOut: () => void;
}) {
  const route = useRoute();
  const library = useLibrary(onSignedOut);
  const byId = library.tracks;
  const tracks = useMemo(() => [...byId.values()], [byId]);
  const [player, audio] = usePlayer(byId, onSignedOut);
  // On a narrow screen the queue opens over the page, from the player.
  const [queueOpen, setQueueOpen] = useState(false);
  const playingId = current(player.queue)?.trackId;
  const playing = playingId === undefined ? undefined : byId.get(playingId);
  // The song being added to Playlists, while its dialog is open, and what was last done.
  const [adding, setAdding] = useState<Track | undefined>(undefined);
  const [notice, setNotice] = useState("");
  const [listingShortcuts, setListingShortcuts] = useState(false);
  const keys = useBindings();
  useEffect(() => {
    if (notice === "") {
      return;
    }
    const fade = setTimeout(() => {
      setNotice("");
    }, NOTICE_MS);
    return () => {
      clearTimeout(fade);
    };
  }, [notice]);
  const actions: TrackActions = {
    onPlay: player.playList,
    onPlayAll: player.playAll,
    onPlayNext: player.playNext,
    onAdd: player.add,
    onFavorite: (track, favorite) => {
      library.setFavorite(track.id, favorite);
    },
    onRate: (track, rating) => {
      library.setRating(track.id, rating);
    },
    onAddToPlaylist: setAdding,
  };
  const addTo = async (track: Track, ids: readonly string[], newNames: readonly string[]) => {
    await library.addToPlaylists(track, ids, newNames);
    const names = [
      ...library.playlists.filter((playlist) => ids.includes(playlist.id)).map((p) => p.name),
      ...newNames,
    ];
    setNotice(`Added “${track.title}” to ${listFormat.format(names)}.`);
  };

  // A shortcut changes what isn't in view, or isn't focused, so what it did is said.
  const shortcuts: ShortcutHandlers = {
    toggle: player.toggle,
    back: () => {
      player.seek(Math.max(0, player.position - SEEK_SECONDS));
    },
    forward: () => {
      player.seek(Math.min(player.duration ?? Infinity, player.position + SEEK_SECONDS));
    },
    previous: () => {
      if (playing !== undefined) {
        player.previous();
      }
    },
    next: () => {
      if (playing !== undefined) {
        player.next();
      }
    },
    volumeDown: () => {
      player.setVolume(stepVolume(player.volume, -1));
    },
    volumeUp: () => {
      player.setVolume(stepVolume(player.volume, 1));
    },
    shuffle: () => {
      player.shuffle(!player.shuffled);
      setNotice(shuffleSaid(!player.shuffled));
    },
    repeat: () => {
      const then = repeatAfter(player.repeat);
      player.setRepeat(then);
      setNotice(REPEATS[then].said);
    },
    favorite: () => {
      if (playing !== undefined) {
        actions.onFavorite(playing, !playing.favorite);
        setNotice(
          playing.favorite
            ? `Removed “${playing.title}” from Favorites.`
            : `Added “${playing.title}” to Favorites.`,
        );
      }
    },
    search: () => {
      document.getElementById("search")?.focus();
    },
    queue: () => {
      if (window.matchMedia(NARROW).matches) {
        setQueueOpen((open) => !open);
      } else {
        document.getElementById("queue")?.focus();
      }
    },
    help: () => {
      setListingShortcuts(true);
    },
  };

  const signOut = () => {
    void api.signOut().finally(onSignedOut);
  };

  return (
    <div className={queueOpen ? "library queue-open" : "library"}>
      <header className="top">
        <h1>
          <a className="wordmark" href={hrefOf({ view: "songs" })}>
            <WaveformIcon weight="bold" aria-hidden />
            medleyplay
          </a>
        </h1>
        <SearchBox route={route} providers={library.providers} />
        <ThemeSwitch />
        <button
          type="button"
          className="icon keys-button"
          aria-label="Keyboard shortcuts"
          {...hintOf("Keyboard shortcuts", keys.help)}
          onClick={() => {
            setListingShortcuts(true);
          }}
        >
          <KeyboardIcon weight="regular" aria-hidden />
        </button>
        <span className="account">{account.display_name}</span>
        <button
          type="button"
          className="icon"
          aria-label="Sign out"
          title="Sign out"
          onClick={signOut}
        >
          <SignOutIcon weight="regular" aria-hidden />
        </button>
      </header>
      <Nav route={route} />
      <main>
        {library.error !== "" && <p role="alert">{library.error}</p>}
        {library.loaded ? (
          <CurrentView
            route={route}
            tracks={tracks}
            playlists={library.playlists}
            playingId={playingId}
            actions={actions}
            admin={account.role === "admin"}
          />
        ) : (
          <p className="empty" aria-busy="true">
            Loading your music…
          </p>
        )}
      </main>
      <QueuePanel player={player} tracks={byId} />
      <PlayerBar
        player={player}
        track={playing}
        onFavorite={actions.onFavorite}
        menuActions={actions}
        queueOpen={queueOpen}
        onToggleQueue={() => {
          setQueueOpen((open) => !open);
        }}
      />
      {adding !== undefined && (
        <AddToPlaylist
          track={adding}
          playlists={library.playlists}
          onSave={(ids, newNames) => addTo(adding, ids, newNames)}
          onClose={() => {
            setAdding(undefined);
          }}
        />
      )}
      {listingShortcuts && (
        <ShortcutList
          onClose={() => {
            setListingShortcuts(false);
          }}
        />
      )}
      <Shortcuts on={shortcuts} />
      <p className="notice" role="status">
        {notice}
      </p>
      <audio ref={audio} preload="auto" />
    </div>
  );
}
