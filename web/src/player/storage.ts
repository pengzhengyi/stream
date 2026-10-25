/**
 * @file What the player keeps in IndexedDB: the queue and its position, and plays not yet sent.
 *
 * Best effort: the browser may refuse IndexedDB or clear it, and then the player
 * starts with an empty queue and sends plays only while the page is open.
 */

import type { Queue } from "./queue";

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
  return run(
    STATE,
    "readonly",
    (objects) => objects.get(QUEUE_KEY) as IDBRequest<Saved | undefined>,
  );
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
