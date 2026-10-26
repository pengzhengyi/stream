/**
 * @file The server's API, as the client uses it: typed requests that throw on failure.
 */

/** Whether a Track can play now, best first. */
export type Availability = "ok" | "offline" | "unavailable" | "missing" | "cant_play";

/** A Track with the signed-in Account's own state. */
export interface Track {
  readonly id: number;
  readonly title: string;
  readonly artist: string;
  readonly album: string;
  readonly album_artist: string;
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
