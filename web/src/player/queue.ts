/**
 * @file The queue: what is playing, what played before it, what plays next, and how.
 *
 * A pure reducer, so the player and its tests share one set of rules. Each entry
 * has its own key, since a Track may be queued more than once. Randomness comes
 * in with the actions that shuffle, so the same numbers give the same order.
 */

/** One place in the queue. */
export interface Entry {
  readonly key: string;
  readonly trackId: number;
}

/** What plays after the last entry, and when a Track ends. */
export type Repeat = "off" | "all" | "one";

/** A source of random numbers in [0, 1), such as `Math.random`. */
export type Random = () => number;

/**
 * The queue's entries, the position of the one playing, and its play modes.
 *
 * A position at the end means the queue has finished: nothing is playing.
 */
export interface Queue {
  readonly entries: readonly Entry[];
  readonly position: number;
  readonly repeat: Repeat;
  /** While shuffled, the queue's own order: the key of every entry, and no others. */
  readonly order: readonly string[] | undefined;
}

/** A change to the queue. */
export type QueueAction =
  | {
      readonly type: "play";
      readonly entries: readonly Entry[];
      readonly start: number;
      readonly random: Random;
    }
  | {
      readonly type: "playAll";
      readonly entries: readonly Entry[];
      readonly shuffled: boolean;
      readonly random: Random;
    }
  | { readonly type: "playNext"; readonly entry: Entry }
  | { readonly type: "add"; readonly entry: Entry }
  | { readonly type: "next" }
  | { readonly type: "previous" }
  | { readonly type: "move"; readonly key: string; readonly to: number }
  | { readonly type: "remove"; readonly key: string }
  | { readonly type: "clear" }
  | { readonly type: "shuffle"; readonly random: Random }
  | { readonly type: "unshuffle" }
  | { readonly type: "repeat"; readonly repeat: Repeat }
  | { readonly type: "restore"; readonly queue: Queue };

/** An empty queue, in order. */
export const EMPTY: Queue = { entries: [], position: 0, repeat: "off", order: undefined };

/** Return the entry playing now, if any. */
export function current(queue: Queue): Entry | undefined {
  return queue.entries[queue.position];
}

/** Return the entries that play after the current one. */
export function upNext(queue: Queue): readonly Entry[] {
  return queue.entries.slice(queue.position + 1);
}

/** Return the entry that plays after the current one, starting over when the queue repeats. */
export function following(queue: Queue): Entry | undefined {
  return current(reduce(queue, { type: "next" }));
}

/** Apply `action` to `queue`. */
export function reduce(queue: Queue, action: QueueAction): Queue {
  const { entries, position, order } = queue;
  switch (action.type) {
    case "play":
      return play(queue, action.entries, action.start, action.random);
    case "playAll":
      // The whole list from its start: in its own order, or every entry at random.
      return {
        ...queue,
        entries: action.shuffled ? inRandomOrder(action.entries, action.random) : action.entries,
        position: 0,
        order: action.shuffled ? action.entries.map((entry) => entry.key) : undefined,
      };
    case "playNext": {
      // In the queue's own order, it follows the Track playing, or ends a finished queue.
      const after = current(queue)?.key;
      const ownPlace =
        order === undefined || after === undefined ? order?.length : order.indexOf(after) + 1;
      return {
        ...queue,
        entries:
          entries.length === 0 ? [action.entry] : insert(entries, position + 1, action.entry),
        position: entries.length === 0 ? 0 : position,
        order: order === undefined ? undefined : insert(order, ownPlace ?? 0, action.entry.key),
      };
    }
    case "add":
      return {
        ...queue,
        entries: [...entries, action.entry],
        position: Math.min(position, entries.length),
        order: order === undefined ? undefined : [...order, action.entry.key],
      };
    case "next": {
      const last = position + 1 >= entries.length;
      return {
        ...queue,
        position: !last ? position + 1 : queue.repeat === "off" ? entries.length : 0,
      };
    }
    case "previous":
      return { ...queue, position: Math.max(position - 1, 0) };
    case "move":
      return move(queue, action.key, action.to);
    case "remove": {
      const index = upcomingIndex(queue, action.key);
      return index === undefined
        ? queue
        : keeping(
            queue,
            entries.filter((_, i) => i !== index),
          );
    }
    case "clear":
      return keeping(queue, entries.slice(0, position + 1));
    case "shuffle":
      return order === undefined ? shuffle(queue, action.random) : queue;
    case "unshuffle":
      return order === undefined ? queue : unshuffle(queue, order);
    case "repeat": {
      // Repeating a finished queue starts it over.
      const finished = position >= entries.length && entries.length > 0;
      return {
        ...queue,
        repeat: action.repeat,
        position: finished && action.repeat !== "off" ? 0 : position,
      };
    }
    case "restore":
      return action.queue;
  }
}

/**
 * Play `list` from its entry `start`, the entries before it already played.
 *
 * Shuffled, nothing in the list has played yet: the chosen entry plays first, then
 * every other one at random.
 */
function play(queue: Queue, list: readonly Entry[], start: number, random: Random): Queue {
  if (queue.order === undefined) {
    return { ...queue, entries: list, position: start };
  }
  const chosen = list[start];
  const others = list.filter((entry) => entry !== chosen);
  return {
    ...queue,
    entries: chosen === undefined ? [] : [chosen, ...inRandomOrder(others, random)],
    position: 0,
    order: list.map((entry) => entry.key),
  };
}

/** Put what plays next in random order, remembering the queue's own; what played stays. */
function shuffle(queue: Queue, random: Random): Queue {
  const played = queue.entries.slice(0, queue.position + 1);
  return {
    ...queue,
    entries: [...played, ...inRandomOrder(upNext(queue), random)],
    order: queue.entries.map((entry) => entry.key),
  };
}

/** Keep only `entries`, and only their keys in the queue's own order. */
function keeping(queue: Queue, entries: readonly Entry[]): Queue {
  const kept = new Set(entries.map((entry) => entry.key));
  return {
    ...queue,
    entries,
    order: queue.order?.filter((key) => kept.has(key)),
  };
}

/** Put the entries back in the queue's own `order`, the current one in its own place. */
function unshuffle(queue: Queue, order: readonly string[]): Queue {
  const place = new Map(order.map((key, i) => [key, i]));
  const placeOf = (entry: Entry) => place.get(entry.key) ?? 0;
  const playing = current(queue);
  const entries = [...queue.entries].sort((a, b) => placeOf(a) - placeOf(b));
  return {
    ...queue,
    entries,
    position: playing === undefined ? entries.length : entries.indexOf(playing),
    order: undefined,
  };
}

/** Return `entries` in random order (Fisher–Yates). */
function inRandomOrder(entries: readonly Entry[], random: Random): Entry[] {
  const result = [...entries];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    const [here, there] = [result[i], result[j]];
    if (here !== undefined && there !== undefined) {
      result[i] = there;
      result[j] = here;
    }
  }
  return result;
}

/** Move an upcoming entry to place `to` among the upcoming ones, 0 being next. */
function move(queue: Queue, key: string, to: number): Queue {
  const from = upcomingIndex(queue, key);
  const moving = from === undefined ? undefined : queue.entries[from];
  // Only what plays next moves, and only among itself.
  if (from === undefined || moving === undefined) {
    return queue;
  }
  const first = queue.position + 1;
  const target = Math.min(Math.max(first + to, first), queue.entries.length - 1);
  if (target === from) {
    return queue;
  }
  const entries = queue.entries.filter((_, i) => i !== from);
  return { ...queue, entries: insert(entries, target, moving) };
}

function upcomingIndex(queue: Queue, key: string): number | undefined {
  const index = queue.entries.findIndex((entry) => entry.key === key);
  return index > queue.position ? index : undefined;
}

function insert<T>(items: readonly T[], index: number, item: T): T[] {
  return [...items.slice(0, index), item, ...items.slice(index)];
}
