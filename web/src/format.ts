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
