import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Track } from "../api";
import { trackOf } from "../testing/server";
import { type TrackActions, TrackTable } from "./TrackTable";

/** Intro, a Long Road that can't play, and Outro, listed in that order, as the server adds them. */
const TRACKS = [
  trackOf(1, "Intro", { duration_ms: 61_000 }),
  trackOf(2, "Long Road", { availability: "missing", duration_ms: 600_000 }),
  trackOf(3, "Outro", { duration_ms: 90_000, rating: 4, favorite: true }),
];

function renderTable(tracks: readonly Track[] = TRACKS, playingId?: number) {
  const actions: TrackActions = {
    onPlay: vi.fn(),
    onPlayAll: vi.fn(),
    onPlayNext: vi.fn(),
    onAdd: vi.fn(),
    onAddToPlaylist: vi.fn(),
    onFavorite: vi.fn(),
    onRate: vi.fn(),
  };
  const view = render(
    <TrackTable
      tracks={tracks}
      playingId={playingId}
      actions={actions}
      empty={<p>No music yet.</p>}
    />,
  );
  return { actions, ...view };
}

const titles = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("button")[1]?.textContent);

beforeEach(() => {
  localStorage.clear();
});

describe("the song table", () => {
  it("plays the Track chosen, with the Tracks in the order shown", async () => {
    const { actions } = renderTable();

    await userEvent.click(screen.getByRole("button", { name: "Outro" }));

    expect(actions.onPlay).toHaveBeenCalledWith(TRACKS, 2);
  });

  it("queues a Track next or last", async () => {
    const { actions } = renderTable();

    await userEvent.click(screen.getByRole("button", { name: "Play Intro next" }));
    await userEvent.click(screen.getByRole("button", { name: "Add Outro to the queue" }));

    expect(actions.onPlayNext).toHaveBeenCalledWith(TRACKS[0]);
    expect(actions.onAdd).toHaveBeenCalledWith(TRACKS[2]);
  });

  it("grays out a Track that can't play, saying why", () => {
    renderTable();

    expect(screen.getByRole("button", { name: "Long Road" })).toBeDisabled();
    expect(screen.getByText("Missing")).toBeInTheDocument();
  });

  it("marks the Track playing", () => {
    renderTable(TRACKS, 3);

    expect(screen.getByRole("button", { name: "Outro" }).closest("tr")).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("shows what it was given when there are no Tracks", () => {
    renderTable([]);

    expect(screen.getByText("No music yet.")).toBeInTheDocument();
  });

  it("counts every Track and the header for screen readers", () => {
    renderTable();

    expect(screen.getByRole("table")).toHaveAttribute("aria-rowcount", "4");
    expect(screen.getByRole("button", { name: "Outro" }).closest("tr")).toHaveAttribute(
      "aria-rowindex",
      "4",
    );
  });
});

describe("sorting", () => {
  it("sorts by a column, then the other way, then back to the order added", async () => {
    renderTable([trackOf(1, "track 10"), trackOf(2, "Banana"), trackOf(3, "track 2")]);
    const title = screen.getByRole("button", { name: "Title" });
    const header = () => screen.getByRole("columnheader", { name: "Title" });

    await userEvent.click(title);
    expect(titles()).toEqual(["Banana", "track 2", "track 10"]);
    expect(header()).toHaveAttribute("aria-sort", "ascending");

    await userEvent.click(title);
    expect(titles()).toEqual(["track 10", "track 2", "Banana"]);
    expect(header()).toHaveAttribute("aria-sort", "descending");

    await userEvent.click(title);
    expect(titles()).toEqual(["track 10", "Banana", "track 2"]);
    expect(header()).not.toHaveAttribute("aria-sort");
  });

  it("sorts times as numbers, shortest first", async () => {
    renderTable();

    await userEvent.click(screen.getByRole("button", { name: "Time" }));

    expect(titles()).toEqual(["Intro", "Outro", "Long Road"]);
  });

  it("plays from the order sorted", async () => {
    const { actions } = renderTable();
    await userEvent.click(screen.getByRole("button", { name: "Time" }));

    await userEvent.click(screen.getByRole("button", { name: "Outro" }));

    expect(actions.onPlay).toHaveBeenCalledWith([TRACKS[0], TRACKS[2], TRACKS[1]], 1);
  });
});

describe("playing them all", () => {
  it("plays every Track that can play, in the order shown", async () => {
    const { actions } = renderTable();
    const title = screen.getByRole("button", { name: "Title" });
    await userEvent.click(title);
    await userEvent.click(title);

    await userEvent.click(screen.getByRole("button", { name: "Play all" }));

    expect(actions.onPlayAll).toHaveBeenCalledExactlyOnceWith([TRACKS[2], TRACKS[0]], false);
  });

  it("shuffles every Track that can play", async () => {
    const { actions } = renderTable();

    await userEvent.click(screen.getByRole("button", { name: "Shuffle all" }));

    expect(actions.onPlayAll).toHaveBeenCalledExactlyOnceWith([TRACKS[0], TRACKS[2]], true);
  });

  it("can't play them all when none can play", () => {
    renderTable([trackOf(2, "Long Road", { availability: "missing" })]);

    expect(screen.getByRole("button", { name: "Play all" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Shuffle all" })).toBeDisabled();
  });
});

describe("favorites and ratings", () => {
  it("marks and clears a favorite with the heart", async () => {
    const { actions } = renderTable();

    await userEvent.click(screen.getByRole("button", { name: "Favorite Intro" }));
    await userEvent.click(screen.getByRole("button", { name: "Favorite Outro" }));

    expect(actions.onFavorite).toHaveBeenCalledWith(TRACKS[0], true);
    expect(actions.onFavorite).toHaveBeenCalledWith(TRACKS[2], false);
    expect(screen.getByRole("button", { name: "Favorite Outro" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("rates with the stars, and clears the rating given by choosing it again", async () => {
    const { actions } = renderTable();
    const stars = (title: string) => within(screen.getByRole("group", { name: `Rate ${title}` }));

    await userEvent.click(stars("Intro").getByRole("button", { name: "2 stars" }));
    await userEvent.click(stars("Outro").getByRole("button", { name: "4 stars" }));

    expect(actions.onRate).toHaveBeenCalledWith(TRACKS[0], 2);
    expect(actions.onRate).toHaveBeenCalledWith(TRACKS[2], null);
  });
});

describe("columns", () => {
  it("hides a column, and remembers it in this browser", async () => {
    const { unmount } = renderTable();

    await userEvent.click(screen.getByText("Columns"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Album" }));
    unmount();
    renderTable();

    expect(screen.queryByRole("columnheader", { name: "Album" })).toBeNull();
    expect(screen.getByRole("columnheader", { name: "Artist" })).toBeInTheDocument();
  });

  it("shows plays and when a Track was added once asked to", async () => {
    renderTable();
    expect(screen.queryByRole("columnheader", { name: "Plays" })).toBeNull();

    await userEvent.click(screen.getByText("Columns"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Plays" }));

    expect(screen.getByRole("columnheader", { name: "Plays" })).toBeInTheDocument();
  });
});
