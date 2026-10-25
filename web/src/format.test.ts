import { describe, expect, it } from "vitest";

import { formatTime } from "./format";

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
