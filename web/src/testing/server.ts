/**
 * @file A stand-in for the server: `fetch` answered from a table of routes.
 */

import { vi } from "vitest";

import type { Account, Track } from "../api";

/** An answer: a status and a JSON body. */
export interface Answer {
  readonly status?: number;
  readonly body?: unknown;
}

/** Routes keyed by method and path, such as `"GET /api/me"`. */
export type Routes = Record<string, Answer | ((body: unknown) => Answer)>;

/** Answer `fetch` from `routes`; any other request answers 404. Returns the calls made. */
export function serve(routes: Routes): { readonly calls: string[] } {
  const calls: string[] = [];
  vi.stubGlobal("fetch", (path: string, init?: RequestInit) => {
    const route = `${init?.method ?? "GET"} ${path}`;
    calls.push(route);
    const found = routes[route];
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const answer = typeof found === "function" ? found(body) : (found ?? { status: 404 });
    const status = answer.status ?? 200;
    return Promise.resolve(
      new Response(status === 204 ? null : JSON.stringify(answer.body ?? { detail: "Not Found" }), {
        status,
      }),
    );
  });
  return { calls };
}

/** Alice, the admin. */
export const ALICE: Account = { id: 1, username: "alice", display_name: "Alice", role: "admin" };

/** A Track that can play, with `title` and the id `id`. */
export function trackOf(id: number, title: string, change: Partial<Track> = {}): Track {
  return {
    id,
    title,
    artist: "The Band",
    album: "Blue",
    album_artist: "",
    duration_ms: 187_000,
    added_at: "2026-10-01T12:00:00Z",
    favorite: false,
    rating: null,
    play_count: 0,
    last_played_at: null,
    availability: "ok",
    downloaded: false,
    ...change,
  };
}

/** The routes of a signed-in server holding `tracks`. */
export function signedIn(tracks: readonly Track[]): Routes {
  return { "GET /api/me": { body: ALICE }, "GET /api/tracks": { body: tracks } };
}
