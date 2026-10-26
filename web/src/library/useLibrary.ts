/**
 * @file The signed-in Account's Tracks: loaded once, asked for again when needed, and written.
 */

import { useEffect, useEffectEvent, useReducer, useRef, useState } from "react";

import { ApiError, type Track, api } from "../api";
import { EMPTY, type Field, reduce, tracksOf } from "./store";

/** The Library as the page sees it. */
export interface Library {
  readonly tracks: ReadonlyMap<number, Track>;
  /** Whether the server has listed the Tracks yet. */
  readonly loaded: boolean;
  /** Why the last request failed, or `""`. */
  readonly error: string;
  readonly setFavorite: (id: number, favorite: boolean) => void;
  readonly setRating: (id: number, rating: number | null) => void;
}

/**
 * Load the Tracks, and ask for them again whenever the page is shown after being
 * hidden, since another device may have changed them.
 *
 * `onSignedOut` runs when a request finds the session has expired.
 */
export function useLibrary(onSignedOut: () => void): Library {
  const [store, dispatch] = useReducer(reduce, EMPTY);
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
    const load = () => {
      api.tracks().then(
        (tracks) => {
          dispatch({ type: "loaded", tracks });
        },
        (failure: unknown) => {
          onFailure(failure);
        },
      );
    };
    const onShown = () => {
      if (document.visibilityState === "visible") {
        load();
      }
    };
    load();
    document.addEventListener("visibilitychange", onShown);
    return () => {
      document.removeEventListener("visibilitychange", onShown);
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
