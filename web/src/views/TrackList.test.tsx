import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { trackOf } from "../testing/server";
import { TrackList } from "./TrackList";

const TRACKS = [
  trackOf(1, "Intro"),
  trackOf(2, "Long Road", { availability: "missing" }),
  trackOf(3, "Outro"),
];

function renderList(playingId?: number) {
  const handlers = { onPlay: vi.fn(), onPlayNext: vi.fn(), onAdd: vi.fn() };
  render(<TrackList tracks={TRACKS} playingId={playingId} {...handlers} />);
  return handlers;
}

describe("TrackList", () => {
  it("plays the Track chosen, by its place in the list", async () => {
    const { onPlay } = renderList();

    await userEvent.click(screen.getByRole("button", { name: "Outro" }));

    expect(onPlay).toHaveBeenCalledWith(2);
  });

  it("queues a Track next or last", async () => {
    const { onPlayNext, onAdd } = renderList();

    await userEvent.click(screen.getByRole("button", { name: "Play Intro next" }));
    await userEvent.click(screen.getByRole("button", { name: "Add Outro to the queue" }));

    expect(onPlayNext).toHaveBeenCalledWith(TRACKS[0]);
    expect(onAdd).toHaveBeenCalledWith(TRACKS[2]);
  });

  it("grays out a Track that can't play, saying why", () => {
    renderList();

    expect(screen.getByRole("button", { name: "Long Road" })).toBeDisabled();
    expect(screen.getByText("Missing")).toBeInTheDocument();
  });

  it("marks the Track playing", () => {
    renderList(3);

    expect(screen.getByRole("button", { name: "Outro" }).closest("tr")).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("says how to add music when there is none", () => {
    render(
      <TrackList
        tracks={[]}
        playingId={undefined}
        onPlay={vi.fn()}
        onPlayNext={vi.fn()}
        onAdd={vi.fn()}
      />,
    );

    expect(screen.getByText(/No music yet/)).toBeInTheDocument();
  });
});
