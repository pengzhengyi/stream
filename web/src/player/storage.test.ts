import { describe, expect, it } from "vitest";

import { EMPTY, type Queue } from "./queue";
import { withModes } from "./storage";

/** A queue playing Track 1 of Tracks 1 and 2, keyed `a` and `b`. */
const ENTRIES = [
  { key: "a", trackId: 1 },
  { key: "b", trackId: 2 },
];

describe("a restored queue", () => {
  it("saved before play modes existed, plays in order without repeating", () => {
    const queue = withModes({ entries: ENTRIES, position: 0 });

    expect(queue).toEqual({ ...EMPTY, entries: ENTRIES });
  });

  it("keeps its play modes", () => {
    const saved: Queue = { entries: ENTRIES, position: 1, repeat: "one", order: ["b", "a"] };

    expect(withModes(saved)).toEqual(saved);
  });

  it("drops a repeat it doesn't know, and an own order that doesn't hold exactly its entries", () => {
    const damaged = { entries: ENTRIES, position: 0, repeat: "twice", order: ["a", "c"] };

    const queue = withModes(damaged as unknown as Queue);

    expect(queue.repeat).toBe("off");
    expect(queue.order).toBeUndefined();
  });
});
