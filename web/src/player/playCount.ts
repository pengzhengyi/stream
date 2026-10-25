/**
 * @file When a Track counts as played, as Last.fm counts a scrobble.
 */

const SHORTEST = 30_000;
const ENOUGH = 240_000;
/** The longest step between two time updates that is still playing, not a seek. */
const LONGEST_STEP = 2;

/**
 * Whether `playedMs` of playing makes a play of a `durationMs`-long Track.
 *
 * Half the Track, or four minutes, whichever is first; a Track shorter than 30
 * seconds never counts.
 */
export function countsAsPlayed(playedMs: number, durationMs: number): boolean {
  return durationMs >= SHORTEST && playedMs >= Math.min(durationMs / 2, ENOUGH);
}

/**
 * Adds up how long a Track has been playing from its position updates.
 *
 * A jump forward or back is a seek, which adds nothing, so seeking to the end
 * doesn't count as listening.
 */
export class PlayTime {
  private last: number | undefined;
  private seconds = 0;

  /** Note the Track's position, in seconds, while it plays. */
  update(position: number): void {
    const step = this.last === undefined ? 0 : position - this.last;
    if (step > 0 && step <= LONGEST_STEP) {
      this.seconds += step;
    }
    this.last = position;
  }

  /** Forget the last position, as after a pause, so the next update adds nothing. */
  pause(): void {
    this.last = undefined;
  }

  /** How long the Track has played, in milliseconds. */
  get playedMs(): number {
    return this.seconds * 1000;
  }
}
