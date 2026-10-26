import { afterEach, describe, expect, it } from "vitest";

import { loadVolume, saveVolume, stepVolume } from "./volume";

describe("stepping the volume", () => {
  it.each([
    [0.5, 1, 0.6],
    [0.5, -1, 0.4],
    [0.9, 1, 1],
    [0.1, -1, 0],
  ] as const)("moves %f one mark %i to %f", (volume, steps, stepped) => {
    expect(stepVolume(volume, steps)).toBe(stepped);
  });

  it.each([
    [0.37, 1, 0.4],
    [0.37, -1, 0.3],
    [0.04, -1, 0],
  ] as const)("moves %f between marks to the next mark %i, %f", (volume, steps, stepped) => {
    expect(stepVolume(volume, steps)).toBe(stepped);
  });

  it.each([
    [1, 1, 1],
    [0, -1, 0],
  ] as const)("stays at %f past the end of the scale", (volume, steps, stepped) => {
    expect(stepVolume(volume, steps)).toBe(stepped);
  });

  it.each([1, 2, 3, 4, 5, 6, 7, 8, 9])(
    "moves from mark %i exactly one mark down and one up",
    (mark) => {
      expect([stepVolume(mark / 10, -1), stepVolume(mark / 10, 1)]).toEqual([
        (mark - 1) / 10,
        (mark + 1) / 10,
      ]);
    },
  );
});

describe("the saved volume", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("comes back as it was saved", () => {
    saveVolume(0.3);

    expect(loadVolume()).toBe(0.3);
  });

  it.each([
    ["none", null],
    ["text", "loud"],
    ["too loud", "1.5"],
    ["negative", "-0.2"],
  ])("is full volume when the saved value is %s", (_, saved) => {
    if (saved !== null) {
      localStorage.setItem("medleyplay.volume.v1", saved);
    }

    expect(loadVolume()).toBe(1);
  });
});
