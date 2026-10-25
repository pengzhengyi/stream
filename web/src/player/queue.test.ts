import { describe, expect, it } from "vitest";

import { EMPTY, type Entry, type Queue, current, reduce, upNext } from "./queue";

/** Entries for Tracks 1, 2, … keyed `a`, `b`, …, as playing a list makes them. */
function entries(...trackIds: number[]): Entry[] {
  return trackIds.map((trackId, i) => ({ key: String.fromCharCode(97 + i), trackId }));
}

/** A queue playing Track 1, with Tracks 2 and 3 next. */
const PLAYING_1_OF_3: Queue = { entries: entries(1, 2, 3), position: 0 };

const tracksOf = (list: readonly Entry[]) => list.map((entry) => entry.trackId);

describe("the queue", () => {
  it("plays a list from its first entry", () => {
    const queue = reduce(EMPTY, { type: "play", entries: entries(4, 5) });

    expect(current(queue)?.trackId).toBe(4);
    expect(tracksOf(upNext(queue))).toEqual([5]);
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
    const finished: Queue = { entries: entries(1), position: 1 };

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

  it("moves an upcoming entry up or down among the upcoming ones", () => {
    const queue = reduce(PLAYING_1_OF_3, { type: "move", key: "c", by: -1 });

    expect(tracksOf(queue.entries)).toEqual([1, 3, 2]);
    expect(reduce(queue, { type: "move", key: "c", by: -1 })).toEqual(queue);
    expect(reduce(queue, { type: "move", key: "b", by: 1 })).toEqual(queue);
  });

  it("never moves or removes the current entry", () => {
    expect(reduce(PLAYING_1_OF_3, { type: "move", key: "a", by: 1 })).toEqual(PLAYING_1_OF_3);
    expect(reduce(PLAYING_1_OF_3, { type: "remove", key: "a" })).toEqual(PLAYING_1_OF_3);
  });

  it("removes an upcoming entry by its key, leaving a repeat of its Track", () => {
    const repeated: Queue = { entries: entries(1, 2, 2), position: 0 };

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
