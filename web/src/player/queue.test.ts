import { describe, expect, it } from "vitest";

import {
  EMPTY,
  type Entry,
  type Queue,
  type QueueAction,
  type Random,
  current,
  following,
  reduce,
  repeatAfter,
  upNext,
} from "./queue";

/** Entries for Tracks 1, 2, … keyed `a`, `b`, …, as playing a list makes them. */
function entries(...trackIds: number[]): Entry[] {
  return trackIds.map((trackId, i) => ({ key: String.fromCharCode(97 + i), trackId }));
}

/** A queue playing Track 1, with Tracks 2 and 3 next. */
const PLAYING_1_OF_3: Queue = { ...EMPTY, entries: entries(1, 2, 3) };

/** A queue in order, playing Track 2 of Tracks 1 to 5. */
const PLAYING_2_OF_5: Queue = { ...EMPTY, entries: entries(1, 2, 3, 4, 5), position: 1 };

/** A random number generator that gives the same numbers for the same seed (mulberry32). */
function seeded(seed: number): Random {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };
}

const SEEDS = Array.from({ length: 20 }, (_, i) => i + 1);

const tracksOf = (list: readonly Entry[]) => list.map((entry) => entry.trackId);
const sorted = (list: readonly number[]) => [...list].sort((a, b) => a - b);

describe("the queue", () => {
  it("plays a list from the chosen entry, the entries before it already played", () => {
    const queue = reduce(EMPTY, {
      type: "play",
      entries: entries(4, 5, 6),
      start: 1,
      random: seeded(1),
    });

    expect(current(queue)?.trackId).toBe(5);
    expect(tracksOf(upNext(queue))).toEqual([6]);
    expect(current(reduce(queue, { type: "previous" }))?.trackId).toBe(4);
  });

  it("puts a Track to play next right after the current one", () => {
    const queue = reduce(PLAYING_1_OF_3, { type: "playNext", entry: { key: "x", trackId: 9 } });

    expect(tracksOf(queue.entries)).toEqual([1, 9, 2, 3]);
    expect(current(queue)?.trackId).toBe(1);
  });

  it("plays a Track asked to play next at once when nothing is queued", () => {
    const queue = reduce(EMPTY, { type: "playNext", entry: { key: "x", trackId: 9 } });

    expect(current(queue)?.trackId).toBe(9);
  });

  it("adds a Track to the end", () => {
    const queue = reduce(PLAYING_1_OF_3, { type: "add", entry: { key: "x", trackId: 9 } });

    expect(tracksOf(queue.entries)).toEqual([1, 2, 3, 9]);
  });

  it("plays a Track added to a finished queue", () => {
    const finished: Queue = { ...EMPTY, entries: entries(1), position: 1 };

    const queue = reduce(finished, { type: "add", entry: { key: "x", trackId: 9 } });

    expect(current(queue)?.trackId).toBe(9);
  });

  it("moves to the next entry, and finishes after the last", () => {
    const second = reduce(PLAYING_1_OF_3, { type: "next" });
    const finished = reduce(reduce(second, { type: "next" }), { type: "next" });

    expect(current(second)?.trackId).toBe(2);
    expect(current(finished)).toBeUndefined();
    expect(reduce(finished, { type: "next" })).toEqual(finished);
  });

  it("goes back to the previous entry, but not before the first", () => {
    const second = reduce(PLAYING_1_OF_3, { type: "next" });

    expect(current(reduce(second, { type: "previous" }))?.trackId).toBe(1);
    expect(reduce(PLAYING_1_OF_3, { type: "previous" })).toEqual(PLAYING_1_OF_3);
  });

  it("moves an upcoming entry to any place among the upcoming ones", () => {
    const playing1Of4: Queue = { ...EMPTY, entries: entries(1, 2, 3, 4) };

    const lastFirst = reduce(playing1Of4, { type: "move", key: "d", to: 0 });
    const firstLast = reduce(playing1Of4, { type: "move", key: "b", to: 2 });

    expect(tracksOf(lastFirst.entries)).toEqual([1, 4, 2, 3]);
    expect(tracksOf(firstLast.entries)).toEqual([1, 3, 4, 2]);
  });

  it("keeps a move within what plays next, and a move to its own place changes nothing", () => {
    const playing2Of4: Queue = { ...EMPTY, entries: entries(1, 2, 3, 4), position: 1 };

    const beforeTheStart = reduce(playing2Of4, { type: "move", key: "d", to: -5 });
    const pastTheEnd = reduce(playing2Of4, { type: "move", key: "c", to: 9 });

    expect(tracksOf(beforeTheStart.entries)).toEqual([1, 2, 4, 3]);
    expect(tracksOf(pastTheEnd.entries)).toEqual([1, 2, 4, 3]);
    expect(reduce(playing2Of4, { type: "move", key: "c", to: 0 })).toBe(playing2Of4);
  });

  it("never moves or removes the current entry, or one already played", () => {
    const playing2Of3: Queue = { ...EMPTY, entries: entries(1, 2, 3), position: 1 };

    expect(reduce(PLAYING_1_OF_3, { type: "move", key: "a", to: 1 })).toEqual(PLAYING_1_OF_3);
    expect(reduce(playing2Of3, { type: "move", key: "a", to: 0 })).toEqual(playing2Of3);
    expect(reduce(PLAYING_1_OF_3, { type: "remove", key: "a" })).toEqual(PLAYING_1_OF_3);
  });

  it("removes an upcoming entry by its key, leaving a repeat of its Track", () => {
    const repeated: Queue = { ...EMPTY, entries: entries(1, 2, 2) };

    const queue = reduce(repeated, { type: "remove", key: "b" });

    expect(queue.entries).toEqual([
      { key: "a", trackId: 1 },
      { key: "c", trackId: 2 },
    ]);
  });

  it("clears what plays next but keeps what is playing and what played", () => {
    const second = reduce(PLAYING_1_OF_3, { type: "next" });

    const queue = reduce(second, { type: "clear" });

    expect(tracksOf(queue.entries)).toEqual([1, 2]);
    expect(current(queue)?.trackId).toBe(2);
  });

  it("restores a saved queue as it was", () => {
    expect(reduce(EMPTY, { type: "restore", queue: PLAYING_1_OF_3 })).toBe(PLAYING_1_OF_3);
  });
});

describe("shuffle", () => {
  it.each(SEEDS)(
    "keeps what played and the Track playing, and plays the rest once each (seed %i)",
    (seed) => {
      const queue = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(seed) });

      expect(tracksOf(queue.entries.slice(0, 2))).toEqual([1, 2]);
      expect(current(queue)?.trackId).toBe(2);
      expect(sorted(tracksOf(upNext(queue)))).toEqual([3, 4, 5]);
    },
  );

  it("plays the other entries in a random order", () => {
    const orders = new Set(
      SEEDS.map((seed) =>
        tracksOf(reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(seed) }).entries).join(),
      ),
    );

    expect(orders.size).toBeGreaterThan(1);
  });

  it("turned off, puts the queue back in its own order, playing on from the Track playing", () => {
    const shuffled = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(1) });
    const later = reduce(reduce(shuffled, { type: "next" }), { type: "next" });

    const queue = reduce(later, { type: "unshuffle" });

    expect(tracksOf(queue.entries)).toEqual([1, 2, 3, 4, 5]);
    expect(current(queue)).toEqual(current(later));
    expect(queue.order).toBeUndefined();
  });

  it("turned on again while on, changes nothing", () => {
    const shuffled = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(1) });

    expect(reduce(shuffled, { type: "shuffle", random: seeded(2) })).toBe(shuffled);
  });

  it("turned off while off, changes nothing", () => {
    expect(reduce(PLAYING_2_OF_5, { type: "unshuffle" })).toBe(PLAYING_2_OF_5);
  });

  it.each(SEEDS)(
    "plays a Track chosen while shuffled first, then the rest of its list (seed %i)",
    (seed) => {
      const shuffled = reduce(PLAYING_1_OF_3, { type: "shuffle", random: seeded(seed) });

      const queue = reduce(shuffled, {
        type: "play",
        entries: entries(4, 5, 6, 7),
        start: 2,
        random: seeded(seed),
      });

      expect(current(queue)?.trackId).toBe(6);
      expect(sorted(tracksOf(upNext(queue)))).toEqual([4, 5, 7]);
      expect(tracksOf(reduce(queue, { type: "unshuffle" }).entries)).toEqual([4, 5, 6, 7]);
    },
  );

  it("puts Play next and Add to queue in the same places in the queue's own order", () => {
    const shuffled = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(1) });
    const nextUp = reduce(shuffled, { type: "playNext", entry: { key: "x", trackId: 8 } });
    const added = reduce(nextUp, { type: "add", entry: { key: "y", trackId: 9 } });

    const queue = reduce(added, { type: "unshuffle" });

    expect(tracksOf(upNext(added))[0]).toBe(8);
    expect(tracksOf(added.entries).at(-1)).toBe(9);
    expect(tracksOf(queue.entries)).toEqual([1, 2, 8, 3, 4, 5, 9]);
  });

  it("forgets a move when turned off, but not a removal", () => {
    const shuffled = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(1) });
    const [first, second] = upNext(shuffled);
    const moved = reduce(shuffled, { type: "move", key: first?.key ?? "", to: 3 });
    const removed = reduce(moved, { type: "remove", key: second?.key ?? "" });

    const queue = reduce(removed, { type: "unshuffle" });

    expect(tracksOf(queue.entries)).toEqual(
      [1, 2, 3, 4, 5].filter((trackId) => trackId !== second?.trackId),
    );
  });
});

describe("playing a whole list", () => {
  it("plays it in its own order from the first entry, turning shuffle off", () => {
    const shuffled = reduce(PLAYING_2_OF_5, { type: "shuffle", random: seeded(1) });

    const queue = reduce(shuffled, {
      type: "playAll",
      entries: entries(4, 5, 6),
      shuffled: false,
      random: seeded(1),
    });

    expect(tracksOf(queue.entries)).toEqual([4, 5, 6]);
    expect(current(queue)?.trackId).toBe(4);
    expect(queue.order).toBeUndefined();
  });

  it.each(SEEDS)("shuffled, plays every entry once and remembers its order (seed %i)", (seed) => {
    const queue = reduce(EMPTY, {
      type: "playAll",
      entries: entries(4, 5, 6, 7),
      shuffled: true,
      random: seeded(seed),
    });

    expect(queue.position).toBe(0);
    expect(sorted(tracksOf(queue.entries))).toEqual([4, 5, 6, 7]);
    expect(tracksOf(reduce(queue, { type: "unshuffle" }).entries)).toEqual([4, 5, 6, 7]);
  });

  it("shuffled, starts from any entry, not always the first", () => {
    const firsts = new Set(
      SEEDS.map(
        (seed) =>
          current(
            reduce(EMPTY, {
              type: "playAll",
              entries: entries(4, 5, 6, 7),
              shuffled: true,
              random: seeded(seed),
            }),
          )?.trackId,
      ),
    );

    expect(firsts.size).toBeGreaterThan(1);
  });

  it("keeps the repeat mode, so repeating an album plays only that album again", () => {
    const repeating = reduce(PLAYING_2_OF_5, { type: "repeat", repeat: "all" });
    const album = reduce(repeating, {
      type: "playAll",
      entries: entries(4, 5),
      shuffled: false,
      random: seeded(1),
    });

    const afterLast = reduce(reduce(album, { type: "next" }), { type: "next" });

    expect(album.repeat).toBe("all");
    expect(current(afterLast)?.trackId).toBe(4);
  });
});

describe("repeat", () => {
  it("cycles off, all, one, and off again", () => {
    expect([repeatAfter("off"), repeatAfter("all"), repeatAfter("one")]).toEqual([
      "all",
      "one",
      "off",
    ]);
  });

  const playingLastOf3: Queue = { ...EMPTY, entries: entries(1, 2, 3), position: 2 };

  it("all plays the first entry after the last", () => {
    const repeating = reduce(playingLastOf3, { type: "repeat", repeat: "all" });

    expect(current(reduce(repeating, { type: "next" }))?.trackId).toBe(1);
    expect(following(repeating)?.trackId).toBe(1);
  });

  it("one still moves on with Next, starting over after the last", () => {
    const repeating = reduce(playingLastOf3, { type: "repeat", repeat: "one" });

    expect(current(reduce(repeating, { type: "next" }))?.trackId).toBe(1);
  });

  it("off finishes after the last, with nothing to follow", () => {
    expect(following(playingLastOf3)).toBeUndefined();
    expect(following(PLAYING_1_OF_3)?.trackId).toBe(2);
  });

  it("all starts a finished queue over", () => {
    const finished: Queue = { ...EMPTY, entries: entries(1, 2), position: 2, repeat: "all" };

    expect(current(reduce(finished, { type: "next" }))?.trackId).toBe(1);
  });

  it("turned on for a finished queue, starts it over", () => {
    const finished: Queue = { ...EMPTY, entries: entries(1, 2), position: 2 };

    expect(current(reduce(finished, { type: "repeat", repeat: "one" }))?.trackId).toBe(1);
    expect(reduce(finished, { type: "repeat", repeat: "off" }).position).toBe(2);
  });
});

describe("any sequence of changes", () => {
  /** Return a random change to make, from `random`. */
  function anyAction(random: Random, made: number): QueueAction {
    const pick = <T>(items: readonly T[]): T => items[Math.floor(random() * items.length)] as T;
    const entry = { key: `n${String(made)}`, trackId: made };
    const some = Math.floor(random() * 6);
    const list = Array.from({ length: some }, (_, i) => ({
      key: `p${String(made)}-${String(i)}`,
      trackId: i,
    }));
    return pick<QueueAction>([
      { type: "play", entries: list, start: Math.floor(random() * some), random },
      { type: "playAll", entries: list, shuffled: random() < 0.5, random },
      { type: "playNext", entry },
      { type: "add", entry },
      { type: "next" },
      { type: "previous" },
      {
        type: "move",
        key: `n${String(Math.floor(random() * made))}`,
        to: Math.floor(random() * 4),
      },
      { type: "remove", key: `n${String(Math.floor(random() * made))}` },
      { type: "clear" },
      { type: "shuffle", random },
      { type: "unshuffle" },
      { type: "repeat", repeat: pick(["off", "all", "one"] as const) },
    ]);
  }

  it.each(SEEDS)(
    "keeps every key once, the position in range, and the own order whole (seed %i)",
    (seed) => {
      const random = seeded(seed);
      let queue = EMPTY;

      for (let made = 0; made < 200; made++) {
        queue = reduce(queue, anyAction(random, made));

        const keys = queue.entries.map((entry) => entry.key);
        expect(new Set(keys).size).toBe(keys.length);
        expect(queue.position).toBeGreaterThanOrEqual(0);
        expect(queue.position).toBeLessThanOrEqual(keys.length);
        if (queue.order !== undefined) {
          expect([...queue.order].sort()).toEqual([...keys].sort());
        }
      }
    },
  );
});
