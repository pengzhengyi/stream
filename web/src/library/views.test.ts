// cspell:ignore supercell ｍｅｌｔ
import { describe, expect, it } from "vitest";

import { trackOf } from "../testing/server";
import {
  albumsOf,
  artistsOf,
  downloadedOf,
  favoritesOf,
  fold,
  search,
  tracksOfAlbum,
  tracksOfArtist,
} from "./views";

/**
 * A small Library:
 *
 * | Title     | Artist      | Album      | Album artist | Length |
 * | --------- | ----------- | ---------- | ------------ | ------ |
 * | Melt      | ryo         | Supercell  |              | 4:00   |
 * | 君の知らない物語 | supercell | Supercell |              | 5:00   |
 * | Untitled  |             |            |              | 1:00   |
 * | しるべのクジラ | ルワン     | くじらと空想  | ルワン         | 4:24   |
 * | Ｍｅｌｔ (live) | RYO     | Live       | Various      | 6:00   |
 */
const LIBRARY = [
  trackOf(1, "Melt", { artist: "ryo", album: "Supercell", duration_ms: 240_000 }),
  trackOf(2, "君の知らない物語", { artist: "supercell", album: "Supercell", duration_ms: 300_000 }),
  trackOf(3, "Untitled", { artist: "", album: "", duration_ms: 60_000 }),
  trackOf(4, "しるべのクジラ", {
    artist: "ルワン",
    album: "くじらと空想",
    album_artist: "ルワン",
    duration_ms: 264_000,
  }),
  trackOf(5, "Ｍｅｌｔ (live)", {
    artist: "RYO",
    album: "Live",
    album_artist: "Various",
    duration_ms: 360_000,
  }),
];

const titles = (tracks: readonly { readonly title: string }[]) => tracks.map((t) => t.title);

describe("folding text for search", () => {
  it("ignores case, width, and hiragana or katakana", () => {
    expect(fold("Ｍｅｌｔ")).toBe("melt");
    expect(fold("ｸｼﾞﾗ")).toBe(fold("くじら"));
    expect(fold("クジラ")).toBe("くじら");
  });

  it("keeps marks that change a kana, so が stays が", () => {
    expect(fold("が")).not.toBe(fold("か"));
  });
});

describe("artists", () => {
  it("lists each artist once, with how many Tracks and how long, names as people read them", () => {
    const artists = artistsOf(LIBRARY);

    expect(artists.map((artist) => [artist.name, artist.count, artist.durationMs])).toEqual([
      ["", 1, 60_000],
      ["ryo", 2, 600_000],
      ["supercell", 1, 300_000],
      ["ルワン", 1, 264_000],
    ]);
  });

  it("opens an artist's Tracks by the name as written, in any case or width", () => {
    expect(titles(tracksOfArtist(LIBRARY, "RYO"))).toEqual(["Melt", "Ｍｅｌｔ (live)"]);
    expect(titles(tracksOfArtist(LIBRARY, ""))).toEqual(["Untitled"]);
  });
});

describe("albums", () => {
  it("lists each album under its album artist, or its artist when that is blank", () => {
    const albums = albumsOf(LIBRARY);

    expect(albums.map((album) => [album.artist, album.name, album.count])).toEqual([
      ["", "", 1],
      ["ryo", "Supercell", 1],
      ["supercell", "Supercell", 1],
      ["Various", "Live", 1],
      ["ルワン", "くじらと空想", 1],
    ]);
  });

  it("opens an album's Tracks by its artist and name", () => {
    expect(titles(tracksOfAlbum(LIBRARY, "ルワン", "くじらと空想"))).toEqual(["しるべのクジラ"]);
    expect(titles(tracksOfAlbum(LIBRARY, "various", "LIVE"))).toEqual(["Ｍｅｌｔ (live)"]);
  });
});

describe("lists made from the Tracks", () => {
  it("lists the favorites, in the order given", () => {
    const tracks = [
      trackOf(1, "A", { favorite: true }),
      trackOf(2, "B"),
      trackOf(3, "C", { favorite: true }),
    ];

    expect(titles(favoritesOf(tracks))).toEqual(["A", "C"]);
  });

  it("lists the Tracks downloaded", () => {
    const tracks = [trackOf(1, "A"), trackOf(2, "B", { downloaded: true })];

    expect(titles(downloadedOf(tracks))).toEqual(["B"]);
  });
});

describe("search", () => {
  it("finds Tracks with every word typed in the title, artist, or album", () => {
    expect(titles(search(LIBRARY, "melt").tracks)).toEqual(["Melt", "Ｍｅｌｔ (live)"]);
    expect(titles(search(LIBRARY, "melt live").tracks)).toEqual(["Ｍｅｌｔ (live)"]);
    expect(titles(search(LIBRARY, "クジラ").tracks)).toEqual(["しるべのクジラ"]);
    expect(titles(search(LIBRARY, "べのくじら").tracks)).toEqual(["しるべのクジラ"]);
  });

  it("finds the artists and albums whose names match", () => {
    const found = search(LIBRARY, "supercell");

    expect(found.artists.map((artist) => artist.name)).toEqual(["supercell"]);
    expect(found.albums.map((album) => [album.artist, album.name])).toEqual([
      ["ryo", "Supercell"],
      ["supercell", "Supercell"],
    ]);
  });

  it("finds nothing for a blank search", () => {
    expect(search(LIBRARY, "   ")).toEqual({ tracks: [], artists: [], albums: [] });
  });
});
