/**
 * @file The position: a bar along the player's top edge to hover, click, or drag.
 *
 * Hovering shows the time under the pointer. A click seeks there at once; a drag
 * follows the pointer and seeks once, where it is let go. The time comes from where
 * the pointer is on the bar, so it lands where it points. Once sent, the bar stays
 * there until the audio reports it has arrived, so it never jumps back first.
 */

import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { formatTime } from "../format";

/** How far an arrow key moves, in seconds. */
const ARROW_SECONDS = 5;
/** How far Page Up or Page Down moves, as a share of the Track. */
const PAGE_SHARE = 0.1;
/** How close the audio must report to where it was sent to have arrived, in seconds. */
const ARRIVED = 1;
/** How long the bar waits for the audio to arrive before showing where it is. */
const GIVE_UP_MS = 2000;

/** Where `position` is in a Track `duration` seconds long, and `onSeek` to move it. */
export function SeekBar({
  position,
  duration,
  onSeek,
}: {
  readonly position: number;
  /** The Track's length in seconds, once known; until then the bar can't move. */
  readonly duration: number | undefined;
  readonly onSeek: (seconds: number) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  // Where a pressed pointer holds the bar, and where a hovering one points.
  const [held, setHeld] = useState<number | undefined>(undefined);
  const [pointed, setPointed] = useState<number | undefined>(undefined);
  // Where the bar last sent the audio, until the audio reports it is there.
  const [sent, setSent] = useState<number | undefined>(undefined);
  if (sent !== undefined && Math.abs(position - sent) < ARRIVED) {
    setSent(undefined);
  }
  useEffect(() => {
    if (sent === undefined) {
      return;
    }
    const giveUp = setTimeout(() => {
      setSent(undefined);
    }, GIVE_UP_MS);
    return () => {
      clearTimeout(giveUp);
    };
  }, [sent]);
  const length = duration ?? 0;
  const movable = length > 0;
  const at = sent ?? position;
  const shown = Math.min(held ?? at, length);
  const tip = held ?? pointed;

  const seek = (seconds: number) => {
    setSent(seconds);
    onSeek(seconds);
  };

  /** Return the time under the pointer at `clientX`, kept within the Track. */
  const timeAt = (clientX: number) => {
    const box = bar.current?.getBoundingClientRect();
    if (box === undefined || box.width === 0) {
      return 0;
    }
    return Math.min(Math.max((clientX - box.left) / box.width, 0), 1) * length;
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!movable || event.button !== 0) {
      return;
    }
    // The bar keeps the pointer while held, wherever it goes.
    event.currentTarget.setPointerCapture(event.pointerId);
    setHeld(timeAt(event.clientX));
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!movable) {
      return;
    }
    const time = timeAt(event.clientX);
    setPointed(time);
    if (held !== undefined) {
      setHeld(time);
    }
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (held === undefined) {
      return;
    }
    seek(timeAt(event.clientX));
    setHeld(undefined);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const to = movable ? keyedTime(event.key, at, length) : undefined;
    if (to !== undefined) {
      event.preventDefault();
      seek(to);
    }
  };

  const share = movable ? shown / length : 0;
  return (
    <div
      ref={bar}
      className="seek"
      role="slider"
      tabIndex={0}
      aria-label="Position"
      aria-valuemin={0}
      aria-valuemax={Math.round(length)}
      aria-valuenow={Math.round(shown)}
      aria-valuetext={`${formatTime(shown)} of ${formatTime(duration)}`}
      aria-disabled={!movable}
      data-held={held === undefined ? undefined : ""}
      style={
        {
          "--played": String(share),
          "--tip": String(tip === undefined || !movable ? 0 : tip / length),
        } as CSSProperties
      }
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => {
        setHeld(undefined);
      }}
      onPointerLeave={() => {
        setPointed(undefined);
      }}
      onKeyDown={onKeyDown}
    >
      <span className="seek-track" aria-hidden>
        {pointed !== undefined && held === undefined && movable && <span className="seek-hover" />}
        <span className="seek-fill" />
      </span>
      <span className="seek-thumb" aria-hidden />
      {tip !== undefined && movable && (
        <span className="seek-tip" aria-hidden>
          {formatTime(tip)}
        </span>
      )}
    </div>
  );
}

/** Return where `key` moves the position, or `undefined` for a key that doesn't move it. */
function keyedTime(key: string, position: number, length: number): number | undefined {
  const within = (seconds: number) => Math.min(Math.max(seconds, 0), length);
  switch (key) {
    case "ArrowRight":
    case "ArrowUp":
      return within(position + ARROW_SECONDS);
    case "ArrowLeft":
    case "ArrowDown":
      return within(position - ARROW_SECONDS);
    case "PageUp":
      return within(position + length * PAGE_SHARE);
    case "PageDown":
      return within(position - length * PAGE_SHARE);
    case "Home":
      return 0;
    case "End":
      return length;
    default:
      return undefined;
  }
}
