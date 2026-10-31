/**
 * @file A song's stretch of a longer file: where it plays, in the file's seconds.
 *
 * A Track that is a file of its own is the whole file. The player shows, seeks, and
 * saves a song's position from its own start, and moves on at its end.
 */

/** Where a song starts and ends in its file, in seconds; `end` is unset when the file's end is. */
export interface Stretch {
  readonly start: number;
  readonly end: number | undefined;
}

/** A whole file. */
export const WHOLE: Stretch = { start: 0, end: undefined };

/** Return the stretch the server's playback answer names. */
export function stretchOf(answer: {
  readonly start_ms: number | null;
  readonly end_ms: number | null;
}): Stretch {
  return {
    start: (answer.start_ms ?? 0) / 1000,
    end: answer.end_ms === null ? undefined : answer.end_ms / 1000,
  };
}

/** Return the position within `stretch` of the file's time `fileSeconds`. */
export function positionIn(stretch: Stretch, fileSeconds: number): number {
  return Math.max(fileSeconds - stretch.start, 0);
}

/** Return how long `stretch` is in a file `fileDuration` seconds long, once that is known. */
export function lengthOf(stretch: Stretch, fileDuration: number): number | undefined {
  const end = stretch.end ?? fileDuration;
  return Number.isFinite(end) ? end - stretch.start : undefined;
}

/** Return the file's time `seconds` into `stretch`, kept within it. */
export function fileTimeOf(stretch: Stretch, seconds: number, fileDuration: number): number {
  const length = lengthOf(stretch, fileDuration);
  const within = Math.max(seconds, 0);
  return stretch.start + (length === undefined ? within : Math.min(within, length));
}

/** Return the seconds left in `stretch` at the file's time `fileSeconds`; unset when the file's end is its end. */
export function remainingIn(stretch: Stretch, fileSeconds: number): number | undefined {
  return stretch.end === undefined ? undefined : stretch.end - fileSeconds;
}
