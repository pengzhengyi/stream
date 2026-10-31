/**
 * @file The signed-in Account's Tracks: loaded once, asked for again when needed, and written.
 */

import { useEffect, useEffectEvent, useReducer, useRef, useState } from "react";

import {
  ApiError,
  type Detail,
  type JobEvent,
  type Mode,
  type Playlist,
  type SongRowIn,
  type Track,
  type VideoRead,
  type VideoText,
  api,
} from "../api";
import { newId } from "../ids";
import { EMPTY, type Field, reduce, tracksOf } from "./store";

/** The Library as the page sees it. */
export interface Library {
  readonly tracks: ReadonlyMap<number, Track>;
  readonly playlists: readonly Playlist[];
  /** The music sites a search could look in, such as `bilibili`. */
  readonly providers: readonly string[];
  /** Whether the server has listed the Tracks yet. */
  readonly loaded: boolean;
  /** Why the last request failed, or `""`. */
  readonly error: string;
  /** Whether medleyplay may contact music sites now, once the server has said. */
  readonly mode: Mode | null;
  readonly setFavorite: (id: number, favorite: boolean) => void;
  readonly setRating: (id: number, rating: number | null) => void;
  /**
   * Change the household's values for the Track, `null` dropping one; the Track then
   * shows the server's answer. The promise rejects with why when the server refuses.
   */
  readonly saveDetails: (
    id: number,
    changes: Partial<Record<Detail, string | number | null>>,
  ) => Promise<void>;
  /**
   * Read a video's pasted text as the Track's `video` values; the Track then shows the
   * server's answer. The promise rejects with why when the server refuses.
   */
  readonly readVideoText: (id: number, text: VideoText) => Promise<VideoRead>;
  /** Make `rows` the songs of the file `id`; the Tracks then show the songs as saved. */
  readonly saveSongs: (
    id: number,
    rows: readonly SongRowIn[],
    known: readonly number[],
  ) => Promise<void>;
  /** Remove every song of the file `id`; the Tracks then show the file whole again. */
  readonly unsplit: (id: number) => Promise<void>;
  /**
   * Add `track` to the end of the Playlists `ids`, and to a new Playlist for each
   * of `newNames`. The Playlists the server saves show at once; the promise rejects
   * with why when it refuses any.
   */
  readonly addToPlaylists: (
    track: Track,
    ids: readonly string[],
    newNames: readonly string[],
  ) => Promise<void>;
}

/** The Jobs whose end can change the Tracks. */
const CHANGES_TRACKS = new Set(["scan_library", "download_source"]);
const FINISHED = new Set<JobEvent["state"]>(["succeeded", "failed", "cancelled"]);
/** How long after the last such Job the Tracks are asked for, so a busy scan asks once. */
const SETTLE_MS = 1000;

/** Compare names as people read them, as the Playlists view lists them. */
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/**
 * Load the Tracks and Playlists, and ask for them again whenever something may
 * have changed them: the page is shown after being hidden, the event stream
 * (re)connects, or a scan or a Download finishes.
 *
 * `onSignedOut` runs when a request finds the session has expired.
 */
export function useLibrary(onSignedOut: () => void): Library {
  const [store, dispatch] = useReducer(reduce, EMPTY);
  const [playlists, setPlaylists] = useState<readonly Playlist[]>([]);
  const [providers, setProviders] = useState<readonly string[]>([]);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<Mode | null>(null);
  const writes = useRef(0);
  // The latest change of each Track's details, so an older read-back can't land after it.
  const latestSave = useRef(new Map<number, number>());

  const failed = (failure: unknown) => {
    if (failure instanceof ApiError && failure.status === 401) {
      onSignedOut();
      return;
    }
    setError(failure instanceof Error ? failure.message : String(failure));
  };
  const onFailure = useEffectEvent(failed);

  useEffect(() => {
    // Each loads on its own, so Playlists that fail to load don't hide the songs.
    const load = () => {
      api.tracks().then(
        (tracks) => {
          dispatch({ type: "loaded", tracks });
        },
        (failure: unknown) => {
          onFailure(failure);
        },
      );
      api.playlists().then(setPlaylists, (failure: unknown) => {
        onFailure(failure);
      });
      api.mode().then(setMode, () => {
        // Without the Mode, the page shows nothing about it until the stream says.
      });
    };
    const onShown = () => {
      if (document.visibilityState === "visible") {
        load();
      }
    };
    load();
    api.features().then(
      (features) => {
        setProviders(features.providers.source_resolver ?? []);
      },
      () => {
        // Without the features, a search looks only in the Library.
      },
    );
    document.addEventListener("visibilitychange", onShown);
    const stopListening = listen(load, setMode);
    return () => {
      document.removeEventListener("visibilitychange", onShown);
      stopListening();
    };
  }, []);

  /** Send `request`, signing out on a 401; then show the Track as the server now has it. */
  const changeDetails = async <T>(id: number, request: Promise<T>): Promise<T> => {
    let answer: T;
    try {
      answer = await request;
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        onSignedOut();
      }
      throw failure;
    }
    // Changed; a Track that can't be read back now shows its new details on the next load.
    const seq = ++writes.current;
    latestSave.current.set(id, seq);
    api.track(id).then(
      (track) => {
        if (latestSave.current.get(id) === seq) {
          dispatch({ type: "details", track });
        }
      },
      () => undefined,
    );
    return answer;
  };

  /** Send `request`, signing out on a 401; then ask for the Tracks again, which it changed. */
  const changeTracks = async (request: Promise<unknown>): Promise<void> => {
    try {
      await request;
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        onSignedOut();
      }
      throw failure;
    }
    api.tracks().then(
      (tracks) => {
        dispatch({ type: "loaded", tracks });
      },
      () => undefined,
    );
  };

  const write = <F extends Field>(id: number, field: F, value: Track[F], send: Promise<Track>) => {
    const seq = ++writes.current;
    dispatch({ type: "write", id, field, value, seq });
    send.then(
      (track) => {
        dispatch({ type: "answered", id, field, value: track[field], seq });
      },
      (failure: unknown) => {
        dispatch({ type: "refused", id, field, seq });
        failed(failure);
      },
    );
  };

  return {
    tracks: tracksOf(store),
    playlists,
    providers,
    loaded: store.loaded,
    error,
    mode,
    setFavorite: (id, favorite) => {
      setError("");
      write(id, "favorite", favorite, api.setFavorite(id, favorite));
    },
    setRating: (id, rating) => {
      setError("");
      write(id, "rating", rating, api.setRating(id, rating));
    },
    saveDetails: async (id, changes) => {
      await changeDetails(id, api.setDetails([id], changes));
    },
    readVideoText: (id, text) => changeDetails(id, api.readVideoText(id, text)),
    saveSongs: async (id, rows, known) => {
      await changeTracks(api.saveSongs(id, rows, known));
    },
    unsplit: async (id) => {
      await changeTracks(api.unsplit(id));
    },
    addToPlaylists: async (track, ids, newNames) => {
      const puts = [
        ...playlists
          .filter((playlist) => ids.includes(playlist.id))
          .map((playlist) =>
            api.putPlaylist(playlist.id, {
              name: playlist.name,
              track_ids: [...playlist.track_ids, track.id],
              keep_downloaded: playlist.keep_downloaded,
            }),
          ),
        ...newNames.map((name) =>
          api.putPlaylist(newId(), { name, track_ids: [track.id], keep_downloaded: false }),
        ),
      ];
      const results = await Promise.allSettled(puts);
      const saved = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : [],
      );
      setPlaylists((now) =>
        listed([...now.filter((each) => !saved.some((s) => s.id === each.id)), ...saved]),
      );
      const refused = results.find((result) => result.status === "rejected");
      if (refused !== undefined) {
        if (refused.reason instanceof ApiError && refused.reason.status === 401) {
          onSignedOut();
        }
        throw refused.reason;
      }
    },
  };
}

/** Return `playlists` as the server lists them: the built-in ones first, then by name. */
function listed(playlists: readonly Playlist[]): Playlist[] {
  return [...playlists].sort(
    (a, b) =>
      Number(a.builtin === null) - Number(b.builtin === null) || collator.compare(a.name, b.name),
  );
}

/**
 * Call `load` when the event stream (re)connects, which may have missed changes,
 * a moment after a scan or a Download finishes, and when the Mode goes Online or
 * Offline, which changes what can play; tell `onMode` each Mode the stream sends.
 * Return what stops listening.
 */
function listen(load: () => void, onMode: (mode: Mode) => void): () => void {
  if (typeof EventSource === "undefined") {
    return () => undefined;
  }
  const events = new EventSource("/api/events");
  let settling: ReturnType<typeof setTimeout> | undefined;
  let connected = false;
  let online: boolean | undefined;
  events.addEventListener("ready", () => {
    // The page loaded on opening; only a reconnect may have missed something.
    if (connected) {
      load();
    }
    connected = true;
  });
  events.addEventListener("mode", (event: MessageEvent<string>) => {
    const mode = JSON.parse(event.data) as Mode;
    if (online !== undefined && online !== mode.online) {
      load();
    }
    online = mode.online;
    onMode(mode);
  });
  events.addEventListener("job", (event: MessageEvent<string>) => {
    const job = JSON.parse(event.data) as JobEvent;
    if (CHANGES_TRACKS.has(job.kind) && FINISHED.has(job.state)) {
      clearTimeout(settling);
      settling = setTimeout(load, SETTLE_MS);
    }
  });
  return () => {
    clearTimeout(settling);
    events.close();
  };
}
