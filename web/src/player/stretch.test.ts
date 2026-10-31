import { describe, expect, it } from "vitest";

import { WHOLE, fileTimeOf, lengthOf, positionIn, remainingIn, stretchOf } from "./stretch";

/** The second song of an album file: from 3:12 to 7:40 of it. */
const NIGHT_DRIVE = stretchOf({ start_ms: 192_000, end_ms: 460_000 });

describe("a song's stretch of its album file", () => {
  it("is the whole file for a Track that is a file of its own", () => {
    expect(stretchOf({ start_ms: null, end_ms: null })).toEqual(WHOLE);
  });

  it("shows its position from its own start, never before it", () => {
    expect(positionIn(NIGHT_DRIVE, 200)).toBe(8);
    expect(positionIn(NIGHT_DRIVE, 190)).toBe(0);
  });

  it("is as long as from its start to its end, or to the file's end for the last song", () => {
    expect(lengthOf(NIGHT_DRIVE, 3600)).toBe(268);
    expect(lengthOf(stretchOf({ start_ms: 460_000, end_ms: null }), 600)).toBe(140);
    expect(lengthOf(WHOLE, Number.NaN)).toBeUndefined();
  });

  it("seeks within itself, from its own start", () => {
    expect(fileTimeOf(NIGHT_DRIVE, 10, 3600)).toBe(202);
    expect(fileTimeOf(NIGHT_DRIVE, -5, 3600)).toBe(192);
    expect(fileTimeOf(NIGHT_DRIVE, 999, 3600)).toBe(460);
  });

  it("says how long it has left, and nothing for a song that ends with its file", () => {
    expect(remainingIn(NIGHT_DRIVE, 450)).toBe(10);
    expect(remainingIn(NIGHT_DRIVE, 461)).toBe(-1);
    expect(remainingIn(WHOLE, 10)).toBeUndefined();
  });
});
