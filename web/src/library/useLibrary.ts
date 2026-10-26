/**
 * @file The signed-in Account's Tracks: loaded once, asked for again when needed, and written.
 */

import { useEffect, useEffectEvent, useReducer, useRef, useState } from "react";

import { ApiError, type JobEvent, type Playlist, type Track, api } from "../api";
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
  readonly setFavorite: (id: number, favorite: boolean) => void;
  readonly setRating: (id: number, rating: number | null) => void;
}

/** The Jobs whose end can change the Tracks. */
const CHANGES_TRACKS = new Set(["scan_library", "download_source"]);
const FINISHED = new Set<JobEvent["state"]>(["succeeded", "failed", "cancelled"]);
/** How long after the last such Job the Tracks are asked for, so a busy scan asks once. */
const SETTLE_MS = 1000;

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
  const writes = useRef(0);

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
    const stopListening = listen(load);
    return () => {
      document.removeEventListener("visibilitychange", onShown);
      stopListening();
    };
  }, []);

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
    setFavorite: (id, favorite) => {
      setError("");
      write(id, "favorite", favorite, api.setFavorite(id, favorite));
    },
    setRating: (id, rating) => {
      setError("");
      write(id, "rating", rating, api.setRating(id, rating));
    },
  };
}

/**
 * Call `load` when the event stream (re)connects, which may have missed changes,
 * and a moment after a scan or a Download finishes. Return what stops listening.
 */
function listen(load: () => void): () => void {
  if (typeof EventSource === "undefined") {
    return () => undefined;
  }
  const events = new EventSource("/api/events");
  let settling: ReturnType<typeof setTimeout> | undefined;
  let connected = false;
  events.addEventListener("ready", () => {
    // The page loaded on opening; only a reconnect may have missed something.
    if (connected) {
      load();
    }
    connected = true;
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
