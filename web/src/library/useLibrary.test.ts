import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { serve, signedIn, trackOf } from "../testing/server";
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
