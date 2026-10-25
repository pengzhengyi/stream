import { describe, expect, it } from "vitest";

import { PlayTime, countsAsPlayed } from "./playCount";

describe("countsAsPlayed", () => {
  it("counts half of a short Track", () => {
    expect(countsAsPlayed(59_000, 120_000)).toBe(false);
    expect(countsAsPlayed(60_000, 120_000)).toBe(true);
  });

  it("counts four minutes of a long Track", () => {
    expect(countsAsPlayed(240_000, 20 * 60_000)).toBe(true);
  });

  it("never counts a Track shorter than 30 seconds", () => {
    expect(countsAsPlayed(29_000, 29_000)).toBe(false);
  });
});

describe("PlayTime", () => {
  it("adds up steady playing", () => {
    const time = new PlayTime();

    for (const position of [0, 0.25, 0.5, 0.75, 1]) {
      time.update(position);
    }

    expect(time.playedMs).toBe(1000);
  });

  it("adds nothing for a seek forward or back", () => {
    const time = new PlayTime();

    for (const position of [0, 1, 90, 91, 10, 11]) {
      time.update(position);
    }

    expect(time.playedMs).toBe(3000);
  });

  it("adds nothing across a pause", () => {
    const time = new PlayTime();
    time.update(0);
    time.update(1);

    time.pause();
    time.update(1.5);
    time.update(2);

    expect(time.playedMs).toBe(1500);
  });
});
