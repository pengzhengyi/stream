/**
 * @file The volume: a button down, a bar to drag, and a button up.
 */

import { SpeakerHighIcon, SpeakerLowIcon, SpeakerSlashIcon } from "@phosphor-icons/react";
import { type CSSProperties, useRef } from "react";

import { stepVolume } from "../player/volume";
import { hintOf, labelsOf, useBindings } from "../shortcuts";
import { useHeldRange } from "./useHeldRange";

/**
 * Change `volume`, from 0 to 1: a button moves it one mark, and the bar once it
 * is let go. While `muted`, the bar says so, and changing the volume turns the
 * sound back on.
 */
export function VolumeControl({
  volume,
  muted = false,
  onVolume,
}: {
  readonly volume: number;
  readonly muted?: boolean;
  readonly onVolume: (volume: number) => void;
}) {
  const bar = useRef<HTMLInputElement>(null);
  const range = useHeldRange(bar, onVolume);
  const shown = range.held ?? volume;
  const percent = Math.round(shown * 100);
  const keys = useBindings();
  return (
    <div className={muted ? "volume muted" : "volume"} role="group" aria-label="Volume">
      <button
        type="button"
        className="icon"
        aria-label="Volume down"
        {...hintOf("Volume down", keys.volumeDown)}
        onClick={() => {
          onVolume(stepVolume(volume, -1));
        }}
      >
        {muted ? (
          <SpeakerSlashIcon weight="regular" aria-hidden />
        ) : (
          <SpeakerLowIcon weight="regular" aria-hidden />
        )}
      </button>
      <input
        ref={bar}
        type="range"
        aria-label="Volume"
        aria-valuetext={muted ? `Muted, ${String(percent)}%` : `${String(percent)}%`}
        title={muted ? `Muted (${labelsOf(keys.mute)} for sound)` : `Volume ${String(percent)}%`}
        min={0}
        max={1}
        step={0.01}
        value={shown}
        style={{ "--played": `${String(percent)}%` } as CSSProperties}
        onChange={range.onChange}
      />
      <button
        type="button"
        className="icon"
        aria-label="Volume up"
        {...hintOf("Volume up", keys.volumeUp)}
        onClick={() => {
          onVolume(stepVolume(volume, 1));
        }}
      >
        <SpeakerHighIcon weight="regular" aria-hidden />
      </button>
    </div>
  );
}
