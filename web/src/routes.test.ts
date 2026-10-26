// cspell:ignore supercell
import { describe, expect, it } from "vitest";

import { type Route, hrefOf, routeOf } from "./routes";

describe("routes", () => {
  it.each<[string, Route]>([
    ["", { view: "songs" }],
    ["#/songs", { view: "songs" }],
    ["#/artists", { view: "artists" }],
    ["#/artist?name=ryo", { view: "artist", name: "ryo" }],
    ["#/albums", { view: "albums" }],
    ["#/album?artist=ryo&name=Supercell", { view: "album", artist: "ryo", name: "Supercell" }],
    ["#/downloaded", { view: "downloaded" }],
    ["#/playlists", { view: "playlists" }],
    ["#/playlist?id=favorites", { view: "playlist", id: "favorites" }],
    ["#/search?q=melt", { view: "search", query: "melt" }],
  ])("reads %s", (hash, route) => {
    expect(routeOf(hash)).toEqual(route);
  });

  it("goes back to the Songs for a route it doesn't know", () => {
    expect(routeOf("#/nowhere")).toEqual({ view: "songs" });
    expect(routeOf("#/artist")).toEqual({ view: "songs" });
  });

  it.each<Route>([
    { view: "artist", name: "初音ミク/米津玄師" },
    { view: "album", artist: "AC/DC & Friends", name: "Back in Black?" },
    { view: "artist", name: "" },
    { view: "search", query: "melt live #1" },
  ])("writes and reads back %o, whatever its names hold", (route) => {
    expect(routeOf(hrefOf(route))).toEqual(route);
  });
});
