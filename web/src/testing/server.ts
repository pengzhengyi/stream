/**
 * @file A stand-in for the server: `fetch` answered from a table of routes.
 */

import { vi } from "vitest";

import type { Account, Features, Playlist, Preferences, Track } from "../api";
import { type SavedShortcuts, openAccount } from "../shortcuts";

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

/** A server with no plugins answering any extension point, and one Account. */
export const NO_FEATURES: Features = { multiple_accounts: false, providers: {} };

/** A Playlist named `name` holding the Tracks `trackIds`, in that order. */
export function playlistOf(id: string, name: string, trackIds: readonly number[]): Playlist {
  return {
    id,
    name,
    track_ids: trackIds,
    rules: null,
    keep_downloaded: false,
    unreadable: "",
    builtin: null,
    updated_at: "2026-10-01T12:00:00Z",
  };
}

/**
 * The Favorites the server keeps for every Account: the smart playlist of its
 * favorite Tracks, here holding `trackIds`.
 */
export function favoritesPlaylistOf(trackIds: readonly number[] = []): Playlist {
  return {
    ...playlistOf("f0000000-0000-4000-8000-000000000001", "Favorites", trackIds),
    rules: { version: 1, match: "all", conditions: [{ field: "favorite", op: "is", value: true }] },
    builtin: "favorites",
  };
}

/** The routes of a signed-in server holding `tracks` and `playlists`, Favorites by default. */
export function signedIn(
  tracks: readonly Track[],
  playlists: readonly Playlist[] = [favoritesPlaylistOf()],
  features: Features = NO_FEATURES,
): Routes {
  return {
    "GET /api/me": { body: ALICE },
    "GET /api/tracks": { body: tracks },
    "GET /api/playlists": { body: playlists },
    "GET /api/features": { body: features },
    ...preferencesOf(),
  };
}

/**
 * The routes of a server keeping `shortcuts` for the signed-in Account, which
 * keeps what the page saves, at the next revision.
 */
export function preferencesOf(shortcuts: SavedShortcuts = null): Routes {
  let kept: Preferences = { shortcuts, revision: shortcuts === null ? 0 : 1 };
  return {
    "GET /api/me/preferences": () => ({ body: kept }),
    "PUT /api/me/preferences": (body) => {
      const sent = body as Preferences;
      kept = { shortcuts: sent.shortcuts, revision: sent.revision + 1 };
      return { body: kept };
    },
  };
}

/** Sign Alice's page in with `shortcuts` saved, as the Library does. */
export async function openWithShortcuts(shortcuts: SavedShortcuts): Promise<void> {
  serve(preferencesOf(shortcuts));
  await openAccount(ALICE.id);
}
