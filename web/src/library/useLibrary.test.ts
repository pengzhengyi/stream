import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  detailsOf,
  favoritesPlaylistOf,
  playlistOf,
  serve,
  signedIn,
  trackOf,
} from "../testing/server";
import { useLibrary } from "./useLibrary";

/** A stand-in for the event stream: the test sends the events the server would. */
class FakeEventSource {
  static last: FakeEventSource | undefined;
  readonly listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.last = this;
  }

  addEventListener(name: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
  }

  send(name: string, data: unknown = {}): void {
    for (const listener of this.listeners.get(name) ?? []) {
      listener(new MessageEvent(name, { data: JSON.stringify(data) }));
    }
  }
}

const stream = () => {
  const found = FakeEventSource.last;
  if (found === undefined) {
    throw new Error("The Library didn't open the event stream.");
  }
  return found;
};

/** How many times the page asked for the Tracks. */
const asked = (calls: readonly string[]) =>
  calls.filter((call) => call === "GET /api/tracks").length;

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  FakeEventSource.last = undefined;
});

describe("the Library", () => {
  it("asks for the Tracks again when the event stream reconnects, not when it first opens", async () => {
    const { calls } = serve(signedIn([trackOf(1, "Intro")]));
    const { result } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });

    act(() => {
      stream().send("ready");
    });
    expect(asked(calls)).toBe(1);
    act(() => {
      stream().send("ready");
    });

    await waitFor(() => {
      expect(asked(calls)).toBe(2);
    });
  });

  it("asks for the Tracks once, a moment after the last scan or Download to finish", async () => {
    const { calls } = serve(signedIn([trackOf(1, "Intro")]));
    const { result } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });
    vi.useFakeTimers();

    act(() => {
      stream().send("job", { id: 1, kind: "scan_library", state: "running" });
      stream().send("job", { id: 1, kind: "scan_library", state: "succeeded" });
      stream().send("job", { id: 2, kind: "download_source", state: "failed" });
      stream().send("job", { id: 3, kind: "cache_source", state: "succeeded" });
    });
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(asked(calls)).toBe(1);
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(asked(calls)).toBe(2);
  });

  it("closes the event stream when the page goes", async () => {
    serve(signedIn([]));
    const { result, unmount } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });

    unmount();

    expect(stream().closed).toBe(true);
  });

  it("puts a refused favorite back, saying why", async () => {
    serve({
      ...signedIn([trackOf(1, "Intro")]),
      "PUT /api/tracks/1/favorite": { status: 404, body: { detail: "No Track has the id 1." } },
    });
    const { result } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });

    act(() => {
      result.current.setFavorite(1, true);
    });
    expect(result.current.tracks.get(1)?.favorite).toBe(true);

    await waitFor(() => {
      expect(result.current.error).toBe("No Track has the id 1.");
    });
    expect(result.current.tracks.get(1)?.favorite).toBe(false);
  });
});

describe("adding a song to Playlists", () => {
  /** Mornings holds Intro; Car is kept downloaded and holds nothing yet. */
  const MORNINGS = playlistOf("p1", "Mornings", [1]);
  const CAR = { ...playlistOf("p2", "Car", []), keep_downloaded: true };

  async function libraryWith(routes: Parameters<typeof serve>[0]) {
    const sent: { path: string; body: unknown }[] = [];
    const answer = (path: string) => (body: unknown) => {
      sent.push({ path, body });
      const playlist = body as { name: string; track_ids: number[]; keep_downloaded: boolean };
      return {
        body: {
          ...playlistOf(path.split("/").at(-1) ?? "", playlist.name, playlist.track_ids),
          keep_downloaded: playlist.keep_downloaded,
        },
      };
    };
    serve({
      ...signedIn(
        [trackOf(1, "Intro"), trackOf(2, "Outro")],
        [favoritesPlaylistOf(), MORNINGS, CAR],
      ),
      "PUT /api/playlists/p1": answer("/api/playlists/p1"),
      "PUT /api/playlists/p2": answer("/api/playlists/p2"),
      ...routes,
    });
    const { result } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.playlists).toHaveLength(3);
    });
    return { result, sent };
  }

  it("puts each Playlist chosen with the song at its end, keeping its Keep downloaded", async () => {
    const { result, sent } = await libraryWith({});

    await act(() => result.current.addToPlaylists(trackOf(2, "Outro"), ["p1", "p2"], []));

    expect(sent).toEqual([
      {
        path: "/api/playlists/p1",
        body: { name: "Mornings", track_ids: [1, 2], keep_downloaded: false },
      },
      { path: "/api/playlists/p2", body: { name: "Car", track_ids: [2], keep_downloaded: true } },
    ]);
    expect(result.current.playlists.map((playlist) => playlist.track_ids)).toEqual([
      [],
      [2],
      [1, 2],
    ]);
  });

  it("makes each new Playlist named, holding just the song, listed by name", async () => {
    const created: unknown[] = [];
    vi.stubGlobal("crypto", { getRandomValues: (bytes: Uint8Array) => bytes.fill(0) });
    const { result } = await libraryWith({
      "PUT /api/playlists/00000000-0000-4000-8000-000000000000": (body: unknown) => {
        created.push(body);
        return { body: playlistOf("00000000-0000-4000-8000-000000000000", "Beach", [2]) };
      },
    });

    await act(() => result.current.addToPlaylists(trackOf(2, "Outro"), [], ["Beach"]));

    expect(created).toEqual([{ name: "Beach", track_ids: [2], keep_downloaded: false }]);
    expect(result.current.playlists.map((playlist) => playlist.name)).toEqual([
      "Favorites",
      "Beach",
      "Car",
      "Mornings",
    ]);
  });

  it("keeps the Playlists the server saved when another is refused, and says why", async () => {
    const { result } = await libraryWith({
      "PUT /api/playlists/p2": {
        status: 409,
        body: { detail: "The Playlist id p2 is already in use." },
      },
    });

    let refused: unknown;
    await act(async () => {
      await result.current
        .addToPlaylists(trackOf(2, "Outro"), ["p1", "p2"], [])
        .catch((failure: unknown) => {
          refused = failure;
        });
    });

    expect(String(refused)).toContain("already in use");

    expect(result.current.playlists.find((playlist) => playlist.id === "p1")?.track_ids).toEqual([
      1, 2,
    ]);
  });
});

describe("saving a song's details", () => {
  async function libraryOf(routes: Parameters<typeof serve>[0]) {
    serve({ ...signedIn([trackOf(7, "BV1dm4y1s7ak")]), ...routes });
    const { result } = renderHook(() => useLibrary(vi.fn()));
    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });
    return result;
  }

  it("sends the household's values, then shows the Track as the server now has it", async () => {
    const sent: unknown[] = [];
    const result = await libraryOf({
      "PUT /api/tracks/7/details": (body: unknown) => {
        sent.push(body);
        return { body: detailsOf(7, { title: "ケビョウニンゲン", year: 2014 }) };
      },
      "GET /api/tracks/7": { body: trackOf(7, "ケビョウニンゲン", { year: 2014 }) },
    });

    await act(() => result.current.saveDetails(7, { title: "ケビョウニンゲン", year: 2014 }));

    expect(sent).toEqual([{ values: { title: "ケビョウニンゲン", year: 2014 } }]);
    expect(result.current.tracks.get(7)).toMatchObject({ title: "ケビョウニンゲン", year: 2014 });
  });

  it("passes on why the server refused, leaving the Track as it was", async () => {
    const result = await libraryOf({
      "PUT /api/tracks/7/details": { status: 422, body: { detail: "year is from 1000 to 2999." } },
    });

    let refused: unknown;
    await act(async () => {
      await result.current.saveDetails(7, { year: 14 }).catch((failure: unknown) => {
        refused = failure;
      });
    });

    expect(String(refused)).toContain("year is from 1000 to 2999.");
    expect(result.current.tracks.get(7)?.title).toBe("BV1dm4y1s7ak");
  });
});
