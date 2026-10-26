/**
 * @file How the page writes times.
 */

/** Write `seconds` as minutes and seconds, such as `3:07`; an unknown length is `–:––`. */
export function formatTime(seconds: number | undefined): string {
  if (seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "–:––";
  }
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60))}:${String(whole % 60).padStart(2, "0")}`;
}

/** Write how many songs there are and how long they play, such as `12 songs, 48 min`. */
export function formatLength(count: number, durationMs: number): string {
  const songs = count === 1 ? "1 song" : `${String(count)} songs`;
  const minutes = Math.round(durationMs / 60_000);
  if (minutes === 0) {
    return songs;
  }
  const hours = Math.floor(minutes / 60);
  const length =
    hours === 0 ? `${String(minutes)} min` : `${String(hours)} hr ${String(minutes % 60)} min`;
  return `${songs}, ${length}`;
}
