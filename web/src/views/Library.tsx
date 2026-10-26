/**
 * @file The signed-in page: the views, the search, the queue, and the player.
 */

import { SignOutIcon, WaveformIcon } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import { type Account, type Track, api } from "../api";
import { useLibrary } from "../library/useLibrary";
import { current } from "../player/queue";
import { usePlayer } from "../player/usePlayer";
import { hrefOf, useRoute } from "../routes";
import { AddToPlaylist } from "./AddToPlaylist";
import { Nav } from "./Nav";
import { PlayerBar } from "./PlayerBar";
import { QueuePanel } from "./QueuePanel";
import { SearchBox } from "./SearchBox";
import { ThemeSwitch } from "./ThemeSwitch";
import type { TrackActions } from "./TrackTable";
import { CurrentView } from "./Views";

/** How long a notice, such as a song added to a Playlist, stays. */
const NOTICE_MS = 4000;
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
  // The song being added to Playlists, while its dialog is open, and what was last done.
  const [adding, setAdding] = useState<Track | undefined>(undefined);
  const [notice, setNotice] = useState("");
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
        track={playingId === undefined ? undefined : byId.get(playingId)}
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
      <p className="notice" role="status">
        {notice}
      </p>
      <audio ref={audio} preload="auto" />
    </div>
  );
}
