/**
 * @file What the player keeps in IndexedDB: the queue and its position, and plays not yet sent.
 *
 * Best effort: the browser may refuse IndexedDB or clear it, and then the player
 * starts with an empty queue and sends plays only while the page is open.
 */

import { EMPTY, type Queue, type Repeat } from "./queue";

/** The queue as it was saved, with how far into the current Track it was. */
export interface Saved {
  readonly queue: Queue;
  readonly seconds: number;
}

/** A play the server hasn't accepted yet. */
export interface Play {
  readonly id: string;
  readonly trackId: number;
  readonly playedAt: string;
}

const NAME = "medleyplay";
const STATE = "state";
const OUTBOX = "outbox";
const QUEUE_KEY = "queue";

let opening: Promise<IDBDatabase | undefined> | undefined;

function database(): Promise<IDBDatabase | undefined> {
  opening ??= new Promise((resolve) => {
    try {
      const request = indexedDB.open(NAME, 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore(STATE);
        request.result.createObjectStore(OUTBOX, { keyPath: "id" });
      };
      request.onsuccess = () => {
        resolve(request.result);
      };
      request.onerror = () => {
        resolve(undefined);
      };
    } catch {
      resolve(undefined);
    }
  });
  return opening;
}

async function run<T>(
  store: string,
  mode: IDBTransactionMode,
  work: (objects: IDBObjectStore) => IDBRequest<T>,
): Promise<T | undefined> {
  const db = await database();
  if (db === undefined) {
    return undefined;
  }
  return new Promise((resolve) => {
    try {
      const request = work(db.transaction(store, mode).objectStore(store));
      request.onsuccess = () => {
        resolve(request.result);
      };
      request.onerror = () => {
        resolve(undefined);
      };
    } catch {
      resolve(undefined);
    }
  });
}

/** Save the queue and the position in its current Track. */
export async function saveQueue(saved: Saved): Promise<void> {
  await run(STATE, "readwrite", (objects) => objects.put(saved, QUEUE_KEY));
}

/** Return the saved queue, if the browser kept one. */
export async function loadQueue(): Promise<Saved | undefined> {
  const saved = await run(
    STATE,
    "readonly",
    (objects) => objects.get(QUEUE_KEY) as IDBRequest<Saved | undefined>,
  );
  return saved === undefined ? undefined : { ...saved, queue: withModes(saved.queue) };
}

const REPEATS: readonly unknown[] = ["off", "all", "one"] satisfies Repeat[];

/**
 * Return `queue` with play modes it can keep: one saved before they existed plays in
 * order, and an own order that doesn't hold exactly its entries is dropped.
 */
export function withModes(queue: Partial<Queue> & Pick<Queue, "entries" | "position">): Queue {
  const keys = queue.entries.map((entry) => entry.key).sort();
  const order: readonly unknown[] | undefined = Array.isArray(queue.order)
    ? queue.order
    : undefined;
  const whole =
    order?.length === keys.length && [...order].sort().every((key, i) => key === keys[i]);
  return {
    entries: queue.entries,
    position: queue.position,
    repeat: REPEATS.includes(queue.repeat) ? (queue.repeat ?? EMPTY.repeat) : EMPTY.repeat,
    order: whole ? queue.order : undefined,
  };
}

/** Keep a play until the server accepts it. */
export async function keepPlay(play: Play): Promise<void> {
  await run(OUTBOX, "readwrite", (objects) => objects.put(play));
}

/** Return the plays not yet sent. */
export async function keptPlays(): Promise<readonly Play[]> {
  return (await run(OUTBOX, "readonly", (objects) => objects.getAll() as IDBRequest<Play[]>)) ?? [];
}

/** Forget a play the server accepted. */
export async function forgetPlay(id: string): Promise<void> {
  await run(OUTBOX, "readwrite", (objects) => objects.delete(id));
}
