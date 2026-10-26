/**
 * @file The signed-in page: the views, the search, the queue, and the player.
 */

import { SignOutIcon, WaveformIcon } from "@phosphor-icons/react";
import { useMemo, useState } from "react";

import { type Account, api } from "../api";
import { useLibrary } from "../library/useLibrary";
import { current } from "../player/queue";
import { usePlayer } from "../player/usePlayer";
import { hrefOf, useRoute } from "../routes";
import { Nav } from "./Nav";
import { PlayerBar } from "./PlayerBar";
import { QueuePanel } from "./QueuePanel";
import { SearchBox } from "./SearchBox";
import { ThemeSwitch } from "./ThemeSwitch";
import type { TrackActions } from "./TrackTable";
import { CurrentView } from "./Views";

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
        queueOpen={queueOpen}
        onToggleQueue={() => {
          setQueueOpen((open) => !open);
        }}
      />
      <audio ref={audio} preload="auto" />
    </div>
  );
}
