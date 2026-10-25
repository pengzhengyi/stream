/**
 * @file The signed-in page: the Track list, the queue, and the player.
 */

import { useEffect, useMemo, useState } from "react";

import { type Account, type Track, api } from "../api";
import { current } from "../player/queue";
import { usePlayer } from "../player/usePlayer";
import { PlayerBar } from "./PlayerBar";
import { QueuePanel } from "./QueuePanel";
import { TrackList } from "./TrackList";

/** Everything a signed-in Account sees. */
export function Library({
  account,
  onSignedOut,
}: {
  readonly account: Account;
  readonly onSignedOut: () => void;
}) {
  const [tracks, setTracks] = useState<readonly Track[]>([]);
  const [error, setError] = useState("");
  const byId = useMemo(() => new Map(tracks.map((track) => [track.id, track])), [tracks]);
  const [player, audio] = usePlayer(byId, onSignedOut);
  const playingId = current(player.queue)?.trackId;

  useEffect(() => {
    api.tracks().then(setTracks, (failure: unknown) => {
      setError(failure instanceof Error ? failure.message : String(failure));
    });
  }, []);

  const signOut = () => {
    void api.signOut().finally(onSignedOut);
  };

  return (
    <div className="library">
      <header className="top">
        <h1>medleyplay</h1>
        <span>{account.display_name}</span>
        <button type="button" onClick={signOut}>
          Sign out
        </button>
      </header>
      <main>
        {error !== "" && <p role="alert">{error}</p>}
        <TrackList
          tracks={tracks}
          playingId={playingId}
          onPlay={(index) => {
            player.playList(tracks, index);
          }}
          onPlayNext={player.playNext}
          onAdd={player.add}
        />
      </main>
      <QueuePanel player={player} tracks={byId} />
      <PlayerBar
        player={player}
        track={playingId === undefined ? undefined : byId.get(playingId)}
      />
      <audio ref={audio} preload="auto" />
    </div>
  );
}
