/**
 * @file The signed-in page: the song table, the queue, and the player.
 */

import { SignOutIcon, WaveformIcon } from "@phosphor-icons/react";
import { useMemo } from "react";

import { type Account, api } from "../api";
import { useLibrary } from "../library/useLibrary";
import { current } from "../player/queue";
import { usePlayer } from "../player/usePlayer";
import { PlayerBar } from "./PlayerBar";
import { QueuePanel } from "./QueuePanel";
import { ThemeSwitch } from "./ThemeSwitch";
import { type TrackActions, TrackTable } from "./TrackTable";

/** Everything a signed-in Account sees. */
export function Library({
  account,
  onSignedOut,
}: {
  readonly account: Account;
  readonly onSignedOut: () => void;
}) {
  const library = useLibrary(onSignedOut);
  const byId = library.tracks;
  const tracks = useMemo(() => [...byId.values()], [byId]);
  const [player, audio] = usePlayer(byId, onSignedOut);
  const playingId = current(player.queue)?.trackId;
  const actions: TrackActions = {
    onPlay: player.playList,
    onPlayNext: player.playNext,
    onAdd: player.add,
    onFavorite: (track, favorite) => {
      library.setFavorite(track.id, favorite);
    },
    onRate: (track, rating) => {
      library.setRating(track.id, rating);
    },
  };

  const signOut = () => {
    void api.signOut().finally(onSignedOut);
  };

  return (
    <div className="library">
      <header className="top">
        <h1>
          <WaveformIcon weight="bold" aria-hidden />
          medleyplay
        </h1>
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
      <main>
        <h2 className="section">Library</h2>
        {library.error !== "" && <p role="alert">{library.error}</p>}
        {library.loaded ? (
          <TrackTable
            tracks={tracks}
            playingId={playingId}
            actions={actions}
            empty={
              <p className="empty">
                No music yet. An admin adds a Library of your own music in{" "}
                <a href="/docs">the API</a>, and its songs appear here.
              </p>
            }
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
      />
      <audio ref={audio} preload="auto" />
    </div>
  );
}
