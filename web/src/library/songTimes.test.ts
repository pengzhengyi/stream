import { describe, expect, it } from "vitest";

import { formatStart, parseStart } from "./songTimes";

describe("a song's start as the editor shows it", () => {
  it("is minutes and seconds, with hours once there are any", () => {
    expect(formatStart(0)).toBe("0:00");
    expect(formatStart(192_000)).toBe("3:12");
    expect(formatStart(4_060_500)).toBe("1:07:40");
  });

  it.each([
    ["3:12", 192_000],
    [" 03:12 ", 192_000],
    ["1:07:40", 4_060_000],
    ["125:30", 7_530_000],
    ["0", 0],
  ])("reads %j as %i ms", (text, ms) => {
    expect(parseStart(text)).toBe(ms);
  });

  it.each(["", "3:75", "1:60:00", "a:12", "3:1", "-1:00"])("reads %j as no start", (text) => {
    expect(parseStart(text)).toBeUndefined();
  });
});
