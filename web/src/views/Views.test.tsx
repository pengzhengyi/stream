// cspell:ignore supercell ｍｅｌｔ
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import {
  type Routes,
  favoritesPlaylistOf,
  playlistOf,
  serve,
  signedIn,
  trackOf,
} from "../testing/server";

/**
 * A Library of three Tracks and one Playlist:
 *
 * | Title     | Artist   | Album    | Album artist | Favorite | Downloaded |
 * | --------- | -------- | -------- | ------------ | -------- | ---------- |
 * | Melt      | ryo      | Supercell |             | yes      |            |
 * | Shiver    | ryo      | Supercell |             |          | yes        |
 * | クジラ     | ルワン    | 空想      | Various     |          |            |
 *
 * The Playlist *Mornings* holds Shiver, then Melt, then Shiver again, after the
 * Favorites the server keeps.
 */
const LIBRARY = [
  trackOf(1, "Melt", { artist: "ryo", album: "Supercell", favorite: true }),
  trackOf(2, "Shiver", { artist: "ryo", album: "Supercell", downloaded: true }),
  trackOf(3, "クジラ", { artist: "ルワン", album: "空想", album_artist: "Various" }),
];

function open(
  hash: string,
  routes: Routes = signedIn(LIBRARY, [
    favoritesPlaylistOf([1]),
    playlistOf("p1", "Mornings", [2, 1, 2]),
  ]),
) {
  history.replaceState(null, "", `/${hash}`);
  serve(routes);
  render(<App />);
}

const songs = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("button")[1]?.textContent);

afterEach(() => {
  history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the views", () => {
  it("opens on Songs, marked in the navigation", async () => {
    open("");

    expect(await screen.findByRole("button", { name: "Melt" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Songs" })).toHaveAttribute("aria-current", "page");
  });

  it("lists the artists, and opens one's songs, with a way back", async () => {
    open("#/artists");

    await userEvent.click(await screen.findByRole("link", { name: /ryo/ }));

    expect(await screen.findByRole("heading", { name: "ryo" })).toBeInTheDocument();
    expect(songs()).toEqual(["Melt", "Shiver"]);
    const nav = screen.getByRole("navigation", { name: "Views" });
    expect(within(nav).getByRole("link", { name: "Artists" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await userEvent.click(within(screen.getByRole("main")).getByRole("link", { name: "Artists" }));
    expect(await screen.findByRole("heading", { name: "Artists" })).toBeInTheDocument();
  });

  it("lists each album under its album artist", async () => {
    open("#/albums");

    expect(
      await screen.findByRole("link", { name: /Supercell.*ryo, 2 songs/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /空想.*Various, 1 song/ })).toBeInTheDocument();
  });

  it("lists only the songs downloaded", async () => {
    open("#/downloaded");

    expect(await screen.findByRole("button", { name: "Shiver" })).toBeInTheDocument();
    expect(songs()).toEqual(["Shiver"]);
  });
});

describe("playlists", () => {
  it("lists the server's Favorites once, first, then the Account's Playlists", async () => {
    open("#/playlists");

    const links = within(await screen.findByRole("list", { name: "Playlists" })).getAllByRole(
      "link",
    );

    expect(links.map((link) => link.textContent)).toEqual([
      "Favorites1 song, 3 min",
      "Mornings3 songs, 9 min",
    ]);
  });

  it("makes Favorites from the hearts, and follows a heart taken away", async () => {
    open("#/playlist?id=favorites", {
      ...signedIn(LIBRARY),
      "PUT /api/tracks/1/favorite": { body: trackOf(1, "Melt", { favorite: false }) },
    });
    expect(await screen.findByRole("button", { name: "Melt" })).toBeInTheDocument();

    await userEvent.click(
      within(screen.getByRole("main")).getByRole("button", { name: "Favorite Melt" }),
    );

    expect(await screen.findByText(/No favorites yet/)).toBeInTheDocument();
  });

  it("plays a Playlist's songs in its order, a song as often as it holds it", async () => {
    open("#/playlist?id=p1");

    expect(await screen.findByRole("heading", { name: "Mornings" })).toBeInTheDocument();
    expect(songs()).toEqual(["Shiver", "Melt", "Shiver"]);
  });
});

describe("search", () => {
  it("finds songs, artists, and albums as you type, ignoring hiragana or katakana", async () => {
    open("");
    await screen.findByRole("button", { name: "Melt" });

    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "くじら");

    const found = await screen.findByRole("region", { name: "Songs found" });
    expect(within(found).getByRole("button", { name: "クジラ" })).toBeInTheDocument();
    expect(location.hash).toBe(`#/search?q=${encodeURIComponent("くじら")}`);
  });

  it("opens a search from its link, the box holding what was searched", async () => {
    open("#/search?q=supercell");

    const albums = await screen.findByRole("region", { name: "Albums found" });

    expect(within(albums).getByRole("link", { name: /Supercell/ })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("supercell");
  });

  it("says when nothing matches", async () => {
    open("#/search?q=nowhere");

    expect(await screen.findByText(/Nothing in your Library matches/)).toBeInTheDocument();
  });

  it("offers a music site a plugin provides as a place to search, not yet to be chosen", async () => {
    open(
      "",
      signedIn(LIBRARY, [], {
        multiple_accounts: false,
        providers: { source_resolver: ["bilibili"] },
      }),
    );

    const scope = await screen.findByRole("radiogroup", { name: "Search in" });

    expect(within(scope).getByRole("radio", { name: "Library" })).toBeChecked();
    expect(within(scope).getByRole("radio", { name: "Bilibili" })).toBeDisabled();
  });

  it("offers no choice of where to search when only the Library can be", async () => {
    open("");
    await screen.findByRole("button", { name: "Melt" });

    expect(screen.queryByRole("radiogroup", { name: "Search in" })).toBeNull();
  });
});
