/**
 * @file The views as hash routes, so Back, Forward, a bookmark, and a reload keep the view.
 *
 * Names travel as query parameters, such as `#/album?artist=AC%2FDC&name=…`, so a
 * name holding `/` or `&` is safe.
 */

import { useEffect, useState } from "react";

/** A view and what it shows. */
export type Route =
  | { readonly view: "songs" }
  | { readonly view: "artists" }
  | { readonly view: "artist"; readonly name: string }
  | { readonly view: "albums" }
  | { readonly view: "album"; readonly artist: string; readonly name: string }
  | { readonly view: "downloaded" }
  | { readonly view: "playlists" }
  | { readonly view: "playlist"; readonly id: string }
  | { readonly view: "search"; readonly query: string };

const SONGS: Route = { view: "songs" };

/** Return the route `hash` names, or the Songs for one it doesn't. */
export function routeOf(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/, "").split("?", 2);
  const params = new URLSearchParams(query);
  const name = params.get("name");
  switch (path) {
    case "songs":
    case "artists":
    case "albums":
    case "downloaded":
    case "playlists":
      return { view: path };
    case "artist":
      return name === null ? SONGS : { view: "artist", name };
    case "album": {
      const artist = params.get("artist");
      return name === null || artist === null ? SONGS : { view: "album", artist, name };
    }
    case "playlist": {
      const id = params.get("id");
      return id === null ? SONGS : { view: "playlist", id };
    }
    case "search":
      return { view: "search", query: params.get("q") ?? "" };
    default:
      return SONGS;
  }
}

/** Return the hash that opens `route`. */
export function hrefOf(route: Route): string {
  switch (route.view) {
    case "artist":
      return `#/artist?${new URLSearchParams({ name: route.name }).toString()}`;
    case "album":
      return `#/album?${new URLSearchParams({ artist: route.artist, name: route.name }).toString()}`;
    case "playlist":
      return `#/playlist?${new URLSearchParams({ id: route.id }).toString()}`;
    case "search":
      return `#/search?${new URLSearchParams({ q: route.query }).toString()}`;
    default:
      return `#/${route.view}`;
  }
}

/** Return the route the page shows now, following Back, Forward, and links. */
export function useRoute(): Route {
  const [route, setRoute] = useState(() => routeOf(location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(routeOf(location.hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return route;
}

/**
 * Show `route`; with `replace`, in place of the view now, so typing a search
 * doesn't leave a Back step for every letter.
 */
export function navigate(route: Route, { replace = false } = {}): void {
  const href = hrefOf(route);
  if (replace) {
    history.replaceState(null, "", href);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    location.hash = href;
  }
}
