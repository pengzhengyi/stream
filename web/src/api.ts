/**
 * @file The server's API, as the client uses it: typed requests that throw on failure.
 */

/** Whether a Track can play now, best first. */
export type Availability =
  "ok" | "offline" | "waiting_online" | "unavailable" | "missing" | "cant_play";

/** A Track with the signed-in Account's own state. */
export interface Track {
  readonly id: number;
  readonly title: string;
  readonly artist: string;
  readonly album: string;
  readonly album_artist: string;
  readonly track_number: number | null;
  readonly disc_number: number | null;
  readonly year: number | null;
  readonly genre: string;
  readonly duration_ms: number | null;
  /** When the Track was added, as an ISO 8601 date and time. */
  readonly added_at: string;
  readonly favorite: boolean;
  /** 1 to 5 stars, or `null` when unrated. */
  readonly rating: number | null;
  readonly play_count: number;
  readonly last_played_at: string | null;
  readonly availability: Availability;
  /** Whether a Source of the Track has a Download kept on the server. */
  readonly downloaded: boolean;
  /** The album file this Track is a song of, if it is one. */
  readonly segment_of: number | null;
  /** Whether this Track's file is split into songs, which then stand for it. */
  readonly split: boolean;
}

/** A detail of a Track the household can edit. */
export type Detail =
  "title" | "artist" | "album" | "album_artist" | "track_number" | "disc_number" | "year" | "genre";

/** Where a value came from, the first shown when several give one. */
export type Origin = "household" | "files" | "musicbrainz" | "video" | "album_file" | "file_name";

/** A value of a detail, and where it came from. */
export interface Found {
  readonly value: string | number;
  readonly origin: Origin;
}

/** A Track's details: what shows, what would show without the household's, and every origin's. */
export interface Details {
  readonly track_id: number;
  readonly shown: Partial<Readonly<Record<Detail, Found>>>;
  readonly found: Partial<Readonly<Record<Detail, Found>>>;
  readonly origins: Partial<
    Readonly<Record<Origin, Partial<Readonly<Record<Detail, string | number>>>>>
  >;
  /** The video's text the `video` values were read from, if any was. */
  readonly video_text: VideoText | null;
}

/** A video's title and description, as the site shows them. */
export interface VideoText {
  readonly title: string;
  readonly description: string;
}

/** A song of a song list: where it starts, its title, and its artist, or "". */
export interface Song {
  readonly start_ms: number;
  readonly title: string;
  readonly artist: string;
}

/** A Track's details once its video's text is read, and the songs that text lists. */
export interface VideoRead {
  readonly details: Details;
  readonly songs: readonly Song[];
}

/** A Playlist; a smart one's Tracks are the ones its rules match now. */
export interface Playlist {
  readonly id: string;
  readonly name: string;
  readonly track_ids: readonly number[];
  readonly rules: Record<string, unknown> | null;
  readonly keep_downloaded: boolean;
  readonly unreadable: string;
  /** Which Playlist the server keeps this is, such as `favorites`; it can't be edited. */
  readonly builtin: "favorites" | null;
  readonly updated_at: string;
}

/** A plain Playlist as it is sent: its name, its Tracks in order, and its Keep downloaded. */
export interface PlainPlaylist {
  readonly name: string;
  readonly track_ids: readonly number[];
  readonly keep_downloaded: boolean;
}

/** What this server can do now: for each extension point, the keys that answer it. */
export interface Features {
  readonly multiple_accounts: boolean;
  readonly providers: Readonly<Record<string, readonly string[]>>;
}

/** A Job as the event stream sends it, as far as the client follows one. */
export interface JobEvent {
  readonly id: number;
  readonly kind: string;
  readonly state: Job["state"];
}

/** The household's settings, and the revision they were read at; 0 if never saved. */
export interface Settings {
  /** The most the Downloads and cache may use, in bytes, or `null` for no limit. */
  readonly storage_limit: number | null;
  readonly removal_order: "least_favorite";
  readonly revision: number;
}

/** An Account's own preferences, and their revision; 0 if never saved. */
export interface Preferences {
  /** The keyboard shortcuts changed from the page's defaults, or `null` for none. */
  readonly shortcuts: Readonly<Record<string, readonly string[]>> | null;
  readonly revision: number;
}

/** What a plan at another storage limit would remove. */
export interface Preview {
  readonly removals: readonly {
    readonly kind: "download" | "cache";
    readonly size: number;
  }[];
}

/** The storage the download policy governs; the figures are `null` when `error` says why. */
export interface Storage {
  readonly limit: number | null;
  readonly downloads: number | null;
  readonly cache: number | null;
  readonly reserved: number | null;
  readonly free: number | null;
  readonly disk_size: number | null;
  readonly wanted: number | null;
  readonly last_evaluation: {
    readonly at: string;
    readonly removed: number;
    readonly started: number;
    readonly shortfalls: readonly unknown[];
    readonly error: string | null;
  } | null;
  readonly error: string | null;
  readonly preview: Preview | null;
}

/** What the admin chose: decide from the network, or always Online or Offline. */
export type ModeSetting = "auto" | "online" | "offline";

/** Why the Mode is what it is. */
export type ModeReason =
  | "set_online"
  | "set_offline"
  | "online"
  | "no_network"
  | "metered"
  | "unknown_network"
  | "unreachable"
  | "settling";

/** Whether medleyplay may contact music sites now, and why. */
export interface Mode {
  readonly setting: ModeSetting;
  readonly online: boolean;
  readonly reason: ModeReason;
  /** The network the server is on, or `null` when there is none or it can't be read. */
  readonly network: {
    readonly kind: "wifi" | "wired" | "unknown";
    readonly metered_as: string | null;
    readonly hotspot_like: boolean;
  } | null;
  readonly since: string;
  readonly checked_at: string | null;
  /** While settling, when the Mode goes Online if nothing changes. */
  readonly online_at: string | null;
  /** How many Jobs wait for Online. */
  readonly held_jobs: number;
}

/** A network an admin marked metered. */
export interface MeteredNetwork {
  readonly id: number;
  readonly name: string;
  readonly subnet: string;
  readonly hotspot_like: boolean;
}

/** The Mode's setting and the metered networks, at their revision; 0 if never saved. */
export interface ModeSettings {
  readonly setting: ModeSetting;
  readonly metered: readonly MeteredNetwork[];
  readonly revision: number;
}

/** The signed-in Account. */
export interface Account {
  readonly id: number;
  readonly username: string;
  readonly display_name: string;
  readonly role: "admin" | "member";
}

/** How a Track can play: from a URL now, once a Job prepares it, or not at all. */
export type PlaybackAnswer =
  | {
      readonly state: "ready";
      readonly source_id: number;
      readonly audio_url: string;
      readonly media_type: string;
    }
  | { readonly state: "preparing"; readonly source_id: number; readonly job_id: number }
  | { readonly state: "unplayable"; readonly availability: Availability };

/** A Job, as far as the player follows one. */
export interface Job {
  readonly id: number;
  readonly state: "waiting" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
  readonly failure_message: string;
}

/** A request the server refused; `status` is its HTTP status. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : response.statusText;
  } catch {
    return response.statusText;
  }
}

/** The routes the client calls. */
export const api = {
  setupStatus: () => call<{ set_up: boolean }>("GET", "/api/setup"),
  setUp: (username: string, displayName: string, password: string) =>
    call<Account>("POST", "/api/setup", { username, display_name: displayName, password }),
  signIn: (username: string, password: string) =>
    call<Account>("POST", "/api/session", { username, password }),
  signOut: () => call<undefined>("DELETE", "/api/session"),
  me: () => call<Account>("GET", "/api/me"),
  tracks: () => call<Track[]>("GET", "/api/tracks"),
  track: (trackId: number) => call<Track>("GET", `/api/tracks/${String(trackId)}`),
  details: (trackId: number) => call<Details>("GET", `/api/tracks/${String(trackId)}/details`),
  /** Set the household's values on the Tracks; `null` drops one. All change, or none. */
  setDetails: (
    trackIds: readonly number[],
    values: Partial<Record<Detail, string | number | null>>,
  ) => call<{ changed: number }>("POST", "/api/tracks/details", { track_ids: trackIds, values }),
  /** Read a video's pasted title and description as the Track's `video` values. */
  readVideoText: (trackId: number, text: VideoText) =>
    call<VideoRead>("POST", `/api/tracks/${String(trackId)}/video-text`, text),
  playlists: () => call<Playlist[]>("GET", "/api/playlists"),
  /** Create or replace a plain Playlist under an id the client chose. */
  putPlaylist: (id: string, playlist: PlainPlaylist) =>
    call<Playlist>("PUT", `/api/playlists/${id}`, playlist),
  features: () => call<Features>("GET", "/api/features"),
  preferences: () => call<Preferences>("GET", "/api/me/preferences"),
  savePreferences: (preferences: Preferences) =>
    call<Preferences>("PUT", "/api/me/preferences", preferences),
  settings: () => call<Settings>("GET", "/api/settings"),
  saveSettings: (settings: Settings) => call<Settings>("PUT", "/api/settings", settings),
  storage: (previewLimit?: number) =>
    call<Storage>(
      "GET",
      previewLimit === undefined ? "/api/storage" : `/api/storage?limit=${String(previewLimit)}`,
    ),
  mode: () => call<Mode>("GET", "/api/mode"),
  modeSettings: () => call<ModeSettings>("GET", "/api/mode/settings"),
  saveModeSetting: (setting: ModeSetting, revision: number) =>
    call<ModeSettings>("PUT", "/api/mode/settings", { setting, revision }),
  /** Mark the network the server is on now metered, as `name`. */
  markMetered: (name: string) => call<MeteredNetwork>("POST", "/api/mode/metered", { name }),
  unmarkMetered: (id: number) => call<undefined>("DELETE", `/api/mode/metered/${String(id)}`),
  setFavorite: (trackId: number, favorite: boolean) =>
    call<Track>("PUT", `/api/tracks/${String(trackId)}/favorite`, { favorite }),
  setRating: (trackId: number, rating: number | null) =>
    call<Track>("PUT", `/api/tracks/${String(trackId)}/rating`, { rating }),
  playback: (trackId: number) =>
    call<PlaybackAnswer>("POST", `/api/tracks/${String(trackId)}/playback`),
  job: (jobId: number) => call<Job>("GET", `/api/jobs/${String(jobId)}`),
  recordPlay: (playId: string, trackId: number, playedAt: string) =>
    call<Track>("PUT", `/api/plays/${playId}`, { track_id: trackId, played_at: playedAt }),
};
