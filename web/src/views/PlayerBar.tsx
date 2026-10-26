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
import { repeatAfter } from "../player/queue";
import type { Player } from "../player/usePlayer";
import { canSetVolume } from "../player/volume";
import { hintOf, useBindings } from "../shortcuts";
import { REPEATS, shuffleSaid } from "./playModes";
import { SeekBar } from "./SeekBar";
import { TrackMenu, type TrackMenuActions } from "./TrackMenu";
import { VolumeControl } from "./VolumeControl";

/** The current Track and its controls. */
export function PlayerBar({
  player,
  track,
  onFavorite,
  menuActions,
  queueOpen,
  onToggleQueue,
}: {
  readonly player: Player;
  readonly track: Track | undefined;
  readonly onFavorite: (track: Track, favorite: boolean) => void;
  readonly menuActions: TrackMenuActions;
  /** Whether the queue is open over the page, as it can be on a narrow screen. */
  readonly queueOpen: boolean;
  readonly onToggleQueue: () => void;
}) {
  const { status, position, duration, shuffled, repeat } = player;
  // A label that changes on a focused button isn't always read out, so the change is said.
  const [said, setSaid] = useState("");
  const playing = status.kind === "playing";
  const keys = useBindings();
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
            {...hintOf(track.favorite ? "Favorite" : "Not a favorite", keys.favorite)}
            onClick={() => {
              onFavorite(track, !track.favorite);
            }}
          >
            <HeartIcon weight={track.favorite ? "fill" : "regular"} aria-hidden />
          </button>
        )}
        {track !== undefined && <TrackMenu track={track} actions={menuActions} queueing={false} />}
      </div>
      <div className="controls">
        <button
          type="button"
          className={shuffled ? "icon mode on" : "icon mode"}
          aria-label="Shuffle"
          aria-pressed={shuffled}
          {...hintOf(shuffled ? "Shuffle: on" : "Shuffle: off", keys.shuffle)}
          onClick={() => {
            player.shuffle(!shuffled);
            setSaid(shuffleSaid(!shuffled));
          }}
        >
          <ShuffleIcon weight={shuffled ? "bold" : "regular"} aria-hidden />
        </button>
        <button
          type="button"
          className="icon"
          aria-label="Previous"
          {...hintOf("Previous", keys.previous)}
          onClick={player.previous}
          disabled={track === undefined}
        >
          <SkipBackIcon weight="fill" aria-hidden />
        </button>
        <button
          type="button"
          className="icon play"
          aria-label={playing ? "Pause" : "Play"}
          {...hintOf(playing ? "Pause" : "Play", keys.toggle)}
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
          {...hintOf("Next", keys.next)}
          onClick={player.next}
          disabled={track === undefined}
        >
          <SkipForwardIcon weight="fill" aria-hidden />
        </button>
        <button
          type="button"
          className={repeat === "off" ? "icon mode" : "icon mode on"}
          aria-label={REPEATS[repeat].label}
          {...hintOf(REPEATS[repeat].label, keys.repeat)}
          onClick={() => {
            const then = repeatAfter(repeat);
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
          {...hintOf("Up next", keys.queue)}
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
