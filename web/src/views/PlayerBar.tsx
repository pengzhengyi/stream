/**
 * @file The player bar: what is playing, its controls, and how far it has got.
 */

import type { Track } from "../api";
import { formatTime } from "../format";
import type { Player } from "../player/usePlayer";

/** The current Track and its controls. */
export function PlayerBar({
  player,
  track,
}: {
  readonly player: Player;
  readonly track: Track | undefined;
}) {
  const { status, position, duration } = player;
  const playing = status.kind === "playing";
  return (
    <section className="player" aria-label="Player">
      <div className="now">
        <strong>{track?.title ?? "Nothing playing"}</strong>
        <span>{track?.artist}</span>
        {status.kind === "preparing" && <span className="note">Preparing…</span>}
        {status.kind === "failed" && (
          <span className="note" role="alert">
            {status.message}
          </span>
        )}
      </div>
      <div className="controls">
        <button type="button" onClick={player.previous} disabled={track === undefined}>
          Previous
        </button>
        <button
          type="button"
          className="play"
          onClick={player.toggle}
          disabled={status.kind !== "playing" && status.kind !== "paused"}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button type="button" onClick={player.next} disabled={track === undefined}>
          Next
        </button>
      </div>
      <div className="progress">
        <span>{formatTime(position)}</span>
        <input
          type="range"
          aria-label="Position"
          min={0}
          max={duration ?? 0}
          step={1}
          value={Math.min(position, duration ?? 0)}
          disabled={duration === undefined}
          onChange={(event) => {
            player.seek(Number(event.currentTarget.value));
          }}
        />
        <span>{formatTime(duration)}</span>
      </div>
    </section>
  );
}
