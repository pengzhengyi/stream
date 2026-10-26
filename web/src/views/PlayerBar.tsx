/**
 * @file The player: what is playing, its controls and play modes, and how far it has got.
 *
 * It floats over the bottom of the page; the position runs along its top edge.
 */

import {
  CircleNotchIcon,
  HeartIcon,
  MusicNotesIcon,
  PauseIcon,
  PlayIcon,
  QueueIcon,
  RepeatIcon,
  RepeatOnceIcon,
  ShuffleIcon,
  SkipBackIcon,
  SkipForwardIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { useState } from "react";

import type { Track } from "../api";
import { formatTime } from "../format";
import type { Repeat } from "../player/queue";
import type { Player } from "../player/usePlayer";
import { canSetVolume } from "../player/volume";
import { SeekBar } from "./SeekBar";
import { VolumeControl } from "./VolumeControl";

/** Each repeat mode: the next one a click chooses, its label, and what is said on choosing it. */
const REPEATS: Record<
  Repeat,
  { readonly then: Repeat; readonly label: string; readonly said: string }
> = {
  off: { then: "all", label: "Repeat: off", said: "Repeat off." },
  all: { then: "one", label: "Repeat: all", said: "Repeating the queue." },
  one: { then: "off", label: "Repeat: one", said: "Repeating this Track." },
};

/** The current Track and its controls. */
export function PlayerBar({
  player,
  track,
  onFavorite,
  queueOpen,
  onToggleQueue,
}: {
  readonly player: Player;
  readonly track: Track | undefined;
  readonly onFavorite: (track: Track, favorite: boolean) => void;
  /** Whether the queue is open over the page, as it can be on a narrow screen. */
  readonly queueOpen: boolean;
  readonly onToggleQueue: () => void;
}) {
  const { status, position, duration, shuffled, repeat } = player;
  // A label that changes on a focused button isn't always read out, so the change is said.
  const [said, setSaid] = useState("");
  const playing = status.kind === "playing";
  return (
    <section className="player" aria-label="Player">
      <SeekBar position={position} duration={duration} onSeek={player.seek} />
      <div className="now">
        <span className="cover" aria-hidden>
          <MusicNotesIcon weight="duotone" />
        </span>
        <div className="names">
          <strong>{track?.title ?? "Nothing playing"}</strong>
          <span>{track?.artist ?? "Choose a Track to play it"}</span>
        </div>
        {track !== undefined && (
          <button
            type="button"
            className={track.favorite ? "icon heart on" : "icon heart"}
            aria-label={`Favorite ${track.title}`}
            aria-pressed={track.favorite}
            title={track.favorite ? "Favorite" : "Not a favorite"}
            onClick={() => {
              onFavorite(track, !track.favorite);
            }}
          >
            <HeartIcon weight={track.favorite ? "fill" : "regular"} aria-hidden />
          </button>
        )}
      </div>
      <div className="controls">
        <button
          type="button"
          className={shuffled ? "icon mode on" : "icon mode"}
          aria-label="Shuffle"
          aria-pressed={shuffled}
          title={shuffled ? "Shuffle: on" : "Shuffle: off"}
          onClick={() => {
            player.shuffle(!shuffled);
            setSaid(shuffled ? "Shuffle off." : "Shuffle on.");
          }}
        >
          <ShuffleIcon weight={shuffled ? "bold" : "regular"} aria-hidden />
        </button>
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
        <button
          type="button"
          className={repeat === "off" ? "icon mode" : "icon mode on"}
          aria-label={REPEATS[repeat].label}
          title={REPEATS[repeat].label}
          onClick={() => {
            const then = REPEATS[repeat].then;
            player.setRepeat(then);
            setSaid(REPEATS[then].said);
          }}
        >
          {repeat === "one" ? (
            <RepeatOnceIcon weight="bold" aria-hidden />
          ) : (
            <RepeatIcon weight={repeat === "all" ? "bold" : "regular"} aria-hidden />
          )}
        </button>
        <span className="visually-hidden" role="status">
          {said}
        </span>
      </div>
      <div className="status">
        <button
          type="button"
          className={queueOpen ? "icon queue-toggle on" : "icon queue-toggle"}
          aria-label="Up next"
          aria-expanded={queueOpen}
          aria-controls="queue"
          title="Up next"
          onClick={onToggleQueue}
        >
          <QueueIcon weight={queueOpen ? "bold" : "regular"} aria-hidden />
        </button>
        {status.kind === "preparing" && <span className="note">Preparing…</span>}
        {status.kind === "failed" && (
          <span className="note failed" role="alert">
            <WarningCircleIcon weight="fill" aria-hidden />
            {status.message}
          </span>
        )}
        {canSetVolume() && <VolumeControl volume={player.volume} onVolume={player.setVolume} />}
        <span className="time">
          {formatTime(position)} <span aria-hidden>/</span> {formatTime(duration)}
        </span>
      </div>
    </section>
  );
}
