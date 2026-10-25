import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { serve, signedIn, trackOf } from "../testing/server";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A signed-in page whose Tracks Intro, Long Road, and Outro are ready to play. */
async function playingIntro() {
  serve({
    ...signedIn([trackOf(1, "Intro"), trackOf(2, "Long Road"), trackOf(3, "Outro")]),
    ...Object.fromEntries(
      [1, 2, 3].map((id) => [
        `POST /api/tracks/${String(id)}/playback`,
        {
          body: {
            state: "ready",
            source_id: id,
            audio_url: `/api/sources/${String(id)}/audio`,
            media_type: "audio/wav",
          },
        },
      ]),
    ),
  });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Intro" }));
}

function upNext(): string[] {
  const queue = screen.getByRole("region", { name: "Up next" });
  return within(queue)
    .queryAllByRole("listitem")
    .map((item) => item.querySelector("span")?.textContent ?? "");
}

describe("the queue", () => {
  it("queues the Tracks after the one chosen", async () => {
    await playingIntro();

    expect(upNext()).toEqual(["Long Road", "Outro"]);
    expect(
      within(screen.getByRole("region", { name: "Player" })).getByText("Intro"),
    ).toBeInTheDocument();
  });

  it("moves and removes what plays next", async () => {
    await playingIntro();

    await userEvent.click(screen.getByRole("button", { name: "Move Outro up" }));
    expect(upNext()).toEqual(["Outro", "Long Road"]);
    await userEvent.click(screen.getByRole("button", { name: "Remove Long Road" }));

    expect(upNext()).toEqual(["Outro"]);
  });

  it("puts a Track asked for next before the rest", async () => {
    await playingIntro();

    await userEvent.click(screen.getByRole("button", { name: "Play Outro next" }));

    expect(upNext()).toEqual(["Outro", "Long Road", "Outro"]);
  });

  it("clears what plays next", async () => {
    await playingIntro();

    await userEvent.click(screen.getByRole("button", { name: "Clear" }));

    expect(screen.getByText("Nothing queued.")).toBeInTheDocument();
  });

  it("moves on to the next Track", async () => {
    await playingIntro();

    await userEvent.click(
      within(screen.getByRole("region", { name: "Player" })).getByRole("button", { name: "Next" }),
    );

    expect(
      within(screen.getByRole("region", { name: "Player" })).getByText("Long Road"),
    ).toBeInTheDocument();
    expect(upNext()).toEqual(["Outro"]);
  });
});
