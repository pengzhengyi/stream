/**
 * @file A stand-in for the server: `fetch` answered from a table of routes.
 */

import { vi } from "vitest";

import type {
  Account,
  Details,
  Features,
  MeteredNetwork,
  Mode,
  ModeSettings,
  Playlist,
  Preferences,
  Track,
  VideoText,
} from "../api";
import { type Origins, type Values, shownOf } from "../library/details";
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
    track_number: null,
    disc_number: null,
    year: null,
    genre: "",
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

/**
 * The origins of a Bilibili album file saved under its video id, with no tags:
 *
 * ```text
 * title    file_name: "BV1dm4y1s7ak"   video: "ケビョウニンゲン"
 * artist   video: "GUMI/MAYU"
 * ```
 */
export const ALBUM_FILE_ORIGINS: Origins = {
  file_name: { title: "BV1dm4y1s7ak" },
  video: { title: "ケビョウニンゲン", artist: "GUMI/MAYU" },
};

/**
 * The origins of a tagged song on a release:
 *
 * ```text
 * files    title "Melt", album "Re:Start", album_artist "MAYU", track_number 3, year 2014
 * ```
 */
export const TAGGED_ORIGINS: Origins = {
  files: { title: "Melt", album: "Re:Start", album_artist: "MAYU", track_number: 3, year: 2014 },
  file_name: { title: "03 Melt" },
};

/**
 * A Track's details from the origins `found`, the album file's by default, with the
 * household's own values `household`, which then show as the server would show them,
 * and the video's text `videoText` the `video` values were read from.
 */
export function detailsOf(
  trackId: number,
  household: Values = {},
  found: Origins = ALBUM_FILE_ORIGINS,
  videoText: VideoText | null = null,
): Details {
  const origins = Object.keys(household).length > 0 ? { household, ...found } : found;
  return {
    track_id: trackId,
    shown: shownOf(origins),
    found: shownOf(found),
    origins,
    video_text: videoText,
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
    "GET /api/mode": { body: modeOf() },
    ...preferencesOf(),
  };
}

/** The Mode: Online on the home Wi-Fi, set to Auto, unless `change` says otherwise. */
export function modeOf(change: Partial<Mode> = {}): Mode {
  return {
    setting: "auto",
    online: true,
    reason: "online",
    network: { kind: "wifi", metered_as: null, hotspot_like: false },
    since: "2026-10-27T12:00:00Z",
    checked_at: "2026-10-27T12:00:00Z",
    online_at: null,
    held_jobs: 0,
    ...change,
  };
}

/**
 * The routes of a server whose Mode is `mode`, keeping the Mode's settings as the
 * page changes them; a network marked is the one the server is on, named as sent.
 */
export function modeSettingsOf(mode: Mode, metered: readonly MeteredNetwork[] = []): Routes {
  let kept: ModeSettings = { setting: mode.setting, metered, revision: metered.length };
  const subnet = mode.network?.hotspot_like === true ? "172.20.10.0/28" : "192.168.31.0/24";
  return {
    "GET /api/mode": { body: mode },
    "GET /api/mode/settings": () => ({ body: kept }),
    "PUT /api/mode/settings": (body) => {
      const sent = body as { setting: Mode["setting"]; revision: number };
      if (sent.revision !== kept.revision) {
        return { status: 409, body: { detail: "The Mode's settings were saved since." } };
      }
      kept = { ...kept, setting: sent.setting, revision: kept.revision + 1 };
      return { body: kept };
    },
    "POST /api/mode/metered": (body) => {
      const { name } = body as { name: string };
      const id = kept.metered.length + 1;
      const network = { id, name, subnet, hotspot_like: mode.network?.hotspot_like ?? false };
      kept = { ...kept, metered: [...kept.metered, network], revision: kept.revision + 1 };
      return { body: network };
    },
    ...Object.fromEntries(
      [1, 2, 3].map((id) => [
        `DELETE /api/mode/metered/${String(id)}`,
        () => {
          kept = { ...kept, metered: kept.metered.filter((each) => each.id !== id) };
          return { status: 204 };
        },
      ]),
    ),
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
