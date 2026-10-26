/**
 * @file The player: what is playing, its controls, and how far it has got.
 *
 * It floats over the bottom of the page; the position runs along its top edge.
 */

import {
  CircleNotchIcon,
  MusicNotesIcon,
  PauseIcon,
  PlayIcon,
  SkipBackIcon,
  SkipForwardIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import type { CSSProperties } from "react";

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
  const length = duration ?? 0;
  const played = length > 0 ? Math.min(position / length, 1) : 0;
  return (
    <section className="player" aria-label="Player">
      <input
        className="seek"
        type="range"
        aria-label="Position"
        min={0}
        max={length}
        step={1}
        value={Math.min(position, length)}
        disabled={duration === undefined}
        style={{ "--played": `${String(played * 100)}%` } as CSSProperties}
        onChange={(event) => {
          player.seek(Number(event.currentTarget.value));
        }}
      />
      <div className="now">
        <span className="cover" aria-hidden>
          <MusicNotesIcon weight="duotone" />
        </span>
        <div className="names">
          <strong>{track?.title ?? "Nothing playing"}</strong>
          <span>{track?.artist ?? "Choose a Track to play it"}</span>
        </div>
      </div>
      <div className="controls">
        <button
          type="button"
          className="icon"
          aria-label="Previous"
          title="Previous"
          onClick={player.previous}
          disabled={track === undefined}
        >
          <SkipBackIcon weight="fill" aria-hidden />
        </button>
        <button
          type="button"
          className="icon play"
          aria-label={playing ? "Pause" : "Play"}
          title={playing ? "Pause" : "Play"}
          onClick={player.toggle}
          disabled={status.kind !== "playing" && status.kind !== "paused"}
        >
          {status.kind === "preparing" ? (
            <CircleNotchIcon weight="bold" className="spin" aria-hidden />
          ) : playing ? (
            <PauseIcon weight="fill" aria-hidden />
          ) : (
            <PlayIcon weight="fill" aria-hidden />
          )}
        </button>
        <button
          type="button"
          className="icon"
          aria-label="Next"
          title="Next"
          onClick={player.next}
          disabled={track === undefined}
        >
          <SkipForwardIcon weight="fill" aria-hidden />
        </button>
      </div>
      <div className="status">
        {status.kind === "preparing" && <span className="note">Preparing…</span>}
        {status.kind === "failed" && (
          <span className="note failed" role="alert">
            <WarningCircleIcon weight="fill" aria-hidden />
            {status.message}
          </span>
        )}
        <span className="time">
          {formatTime(position)} <span aria-hidden>/</span> {formatTime(duration)}
        </span>
      </div>
    </section>
  );
}
