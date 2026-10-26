/**
 * @file The player's volume: a scale of ten marks the buttons step along, and where it is kept.
 *
 * The volume is this browser's own, so it lives in `localStorage` rather than on the server.
 */

/** How many steps the volume buttons take from silent to full. */
const MARKS = 10;
const SAVED = "medleyplay.volume.v1";

/** Return the volume one mark down (-1) or up (1) from `volume`, within silent and full. */
export function stepVolume(volume: number, steps: -1 | 1): number {
  const at = volume * MARKS;
  // Between two marks, one step reaches the next mark that way.
  const mark = steps > 0 ? Math.floor(at) + 1 : Math.ceil(at) - 1;
  return Math.min(Math.max(mark, 0), MARKS) / MARKS;
}

/** Return the volume this browser last kept, or full volume. */
export function loadVolume(): number {
  try {
    const saved = Number(localStorage.getItem(SAVED) ?? Number.NaN);
    if (Number.isFinite(saved) && saved >= 0 && saved <= 1) {
      return saved;
    }
  } catch {
    // A browser that can't keep it starts at full volume.
  }
  return 1;
}

/** Keep `volume` for the next visit. */
export function saveVolume(volume: number): void {
  try {
    localStorage.setItem(SAVED, String(volume));
  } catch {
    // Best effort: the next visit starts at full volume.
  }
}

let adjustable: boolean | undefined;

/** Return whether this browser lets a page set the volume; iOS leaves it to the device. */
export function canSetVolume(): boolean {
  if (adjustable === undefined) {
    try {
      const probe = new Audio();
      probe.volume = 0.5;
      adjustable = probe.volume === 0.5;
    } catch {
      adjustable = false;
    }
  }
  return adjustable;
}
