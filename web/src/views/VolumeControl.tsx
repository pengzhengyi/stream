/**
 * @file The volume: a button down, a bar to drag, and a button up.
 */

import { SpeakerHighIcon, SpeakerLowIcon } from "@phosphor-icons/react";
import { type CSSProperties, useRef } from "react";

import { stepVolume } from "../player/volume";
import { useHeldRange } from "./useHeldRange";

/** Change `volume`, from 0 to 1: a button moves it one mark, and the bar once it is let go. */
export function VolumeControl({
  volume,
  onVolume,
}: {
  readonly volume: number;
  readonly onVolume: (volume: number) => void;
}) {
  const bar = useRef<HTMLInputElement>(null);
  const range = useHeldRange(bar, onVolume);
  const shown = range.held ?? volume;
  const percent = Math.round(shown * 100);
  return (
    <div className="volume" role="group" aria-label="Volume">
      <button
        type="button"
        className="icon"
        aria-label="Volume down"
        title="Volume down"
        onClick={() => {
          onVolume(stepVolume(volume, -1));
        }}
      >
        <SpeakerLowIcon weight="regular" aria-hidden />
      </button>
      <input
        ref={bar}
        type="range"
        aria-label="Volume"
        aria-valuetext={`${String(percent)}%`}
        title={`Volume ${String(percent)}%`}
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
        title="Volume up"
        onClick={() => {
          onVolume(stepVolume(volume, 1));
        }}
      >
        <SpeakerHighIcon weight="regular" aria-hidden />
      </button>
    </div>
  );
}
