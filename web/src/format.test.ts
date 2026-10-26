import { describe, expect, it } from "vitest";

import { formatLength, formatTime } from "./format";

describe("formatTime", () => {
  it("writes minutes and two-digit seconds", () => {
    expect(formatTime(187.9)).toBe("3:07");
    expect(formatTime(0)).toBe("0:00");
  });

  it("writes an unknown length as dashes", () => {
    expect(formatTime(undefined)).toBe("–:––");
    expect(formatTime(Number.NaN)).toBe("–:––");
  });
});

describe("formatLength", () => {
  it("writes how many songs and how long they play, in minutes or hours", () => {
    expect(formatLength(1, 240_000)).toBe("1 song, 4 min");
    expect(formatLength(12, 2_880_000)).toBe("12 songs, 48 min");
    expect(formatLength(30, 6_300_000)).toBe("30 songs, 1 hr 45 min");
  });

  it("leaves the length out when it is unknown", () => {
    expect(formatLength(2, 0)).toBe("2 songs");
  });
});
