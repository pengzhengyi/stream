/**
 * @file A song's start in the songs editor: `3:12`, or `1:07:40` past the first hour.
 */

/** Return `ms` as the editor shows a start, dropping any part of a second. */
export function formatStart(ms: number): string {
  const total = Math.floor(ms / 1000);
  const [hours, minutes, seconds] = [
    Math.floor(total / 3600),
    Math.floor(total / 60) % 60,
    total % 60,
  ];
  const twoDigits = (value: number) => String(value).padStart(2, "0");
  return hours > 0
    ? `${String(hours)}:${twoDigits(minutes)}:${twoDigits(seconds)}`
    : `${String(minutes)}:${twoDigits(seconds)}`;
}

/** Return the start `text` names in milliseconds, or nothing when it names none. */
export function parseStart(text: string): number | undefined {
  const parts = text.trim().split(":");
  if (parts.length > 3 || !parts.every((part) => /^\d+$/.test(part))) {
    return undefined;
  }
  const [seconds = 0, minutes = 0, hours = 0] = [...parts].reverse().map(Number);
  const twoDigitSeconds = parts.length === 1 || parts[parts.length - 1]?.length === 2;
  if (seconds >= 60 || !twoDigitSeconds || (parts.length === 3 && minutes >= 60)) {
    return undefined;
  }
  return ((hours * 60 + minutes) * 60 + seconds) * 1000;
}
