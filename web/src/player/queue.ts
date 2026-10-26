/**
 * @file The queue: what is playing, what played before it, and what plays next.
 *
 * A pure reducer, so the player and its tests share one set of rules. Each entry
 * has its own key, since a Track may be queued more than once.
 */

/** One place in the queue. */
export interface Entry {
  readonly key: string;
  readonly trackId: number;
}

/**
 * The queue's entries, and the position of the one playing.
 *
 * A position at the end means the queue has finished: nothing is playing.
 */
export interface Queue {
  readonly entries: readonly Entry[];
  readonly position: number;
}

/** A change to the queue. */
export type QueueAction =
  | { readonly type: "play"; readonly entries: readonly Entry[] }
  | { readonly type: "playNext"; readonly entry: Entry }
  | { readonly type: "add"; readonly entry: Entry }
  | { readonly type: "next" }
  | { readonly type: "previous" }
  | { readonly type: "move"; readonly key: string; readonly to: number }
  | { readonly type: "remove"; readonly key: string }
  | { readonly type: "clear" }
  | { readonly type: "restore"; readonly queue: Queue };

/** An empty queue. */
export const EMPTY: Queue = { entries: [], position: 0 };

/** Return the entry playing now, if any. */
export function current(queue: Queue): Entry | undefined {
  return queue.entries[queue.position];
}

/** Return the entries that play after the current one. */
export function upNext(queue: Queue): readonly Entry[] {
  return queue.entries.slice(queue.position + 1);
}

/** Apply `action` to `queue`. */
export function reduce(queue: Queue, action: QueueAction): Queue {
  const { entries, position } = queue;
  switch (action.type) {
    case "play":
      return { entries: action.entries, position: 0 };
    case "playNext":
      return entries.length === 0
        ? { entries: [action.entry], position: 0 }
        : { entries: insert(entries, position + 1, action.entry), position };
    case "add":
      return { entries: [...entries, action.entry], position: Math.min(position, entries.length) };
    case "next":
      return { entries, position: Math.min(position + 1, entries.length) };
    case "previous":
      return { entries, position: Math.max(position - 1, 0) };
    case "move":
      return move(queue, action.key, action.to);
    case "remove": {
      const index = upcomingIndex(queue, action.key);
      return index === undefined
        ? queue
        : { entries: entries.filter((_, i) => i !== index), position };
    }
    case "clear":
      return { entries: entries.slice(0, position + 1), position };
    case "restore":
      return action.queue;
  }
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
  return { entries: insert(entries, target, moving), position: queue.position };
}

function upcomingIndex(queue: Queue, key: string): number | undefined {
  const index = queue.entries.findIndex((entry) => entry.key === key);
  return index > queue.position ? index : undefined;
}

function insert(entries: readonly Entry[], index: number, entry: Entry): Entry[] {
  return [...entries.slice(0, index), entry, ...entries.slice(index)];
}
