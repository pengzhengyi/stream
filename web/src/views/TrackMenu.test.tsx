// cspell:ignore supercell
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { trackOf } from "../testing/server";
import { TrackMenu, type TrackMenuActions } from "./TrackMenu";

/** Melt by ryo, on the album Supercell, which is listed under its album artist, supercell. */
const MELT = trackOf(1, "Melt", { artist: "ryo", album: "Supercell", album_artist: "supercell" });

function renderMenu(queueing = true) {
  const actions: TrackMenuActions = {
    onPlayNext: vi.fn(),
    onAdd: vi.fn(),
    onAddToPlaylist: vi.fn(),
    onEditDetails: vi.fn(),
  };
  render(<TrackMenu track={MELT} actions={actions} queueing={queueing} />);
  return actions;
}

const open = async () => {
  await userEvent.click(screen.getByRole("button", { name: "More actions for Melt" }));
  return screen.findByRole("menu");
};

afterEach(() => {
  history.replaceState(null, "", "/");
});

describe("a song's menu", () => {
  it("holds its less frequent actions, each an icon and words", async () => {
    renderMenu();

    await open();

    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Play next",
      "Add to queue",
      "Go to artist",
      "Go to album",
      "Add to playlist…",
      "Edit details…",
    ]);
  });

  it("leaves out queueing for the song playing", async () => {
    renderMenu(false);

    await open();

    expect(screen.queryByRole("menuitem", { name: "Play next" })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Go to album" })).toBeInTheDocument();
  });

  it("goes to the song's artist", async () => {
    renderMenu();
    await open();

    await userEvent.click(screen.getByRole("menuitem", { name: "Go to artist" }));

    expect(location.hash).toBe("#/artist?name=ryo");
  });

  it("goes to the song's album, under its album artist", async () => {
    renderMenu();
    await open();

    await userEvent.click(screen.getByRole("menuitem", { name: "Go to album" }));

    expect(location.hash).toBe("#/album?artist=supercell&name=Supercell");
  });

  it.each([
    ["Play next", "onPlayNext"],
    ["Add to queue", "onAdd"],
    ["Add to playlist…", "onAddToPlaylist"],
    ["Edit details…", "onEditDetails"],
  ] as const)("%s acts on the song, and closes the menu", async (item, action) => {
    const actions = renderMenu();
    await open();

    await userEvent.click(screen.getByRole("menuitem", { name: item }));

    expect(actions[action]).toHaveBeenCalledExactlyOnceWith(MELT);
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
  });

  it("opens from the keyboard, moves with the arrows, and acts with Enter", async () => {
    const actions = renderMenu();
    screen.getByRole("button", { name: "More actions for Melt" }).focus();

    await userEvent.keyboard("{Enter}");
    await screen.findByRole("menu");
    await userEvent.keyboard("{ArrowDown}{Enter}");

    expect(actions.onAdd).toHaveBeenCalledExactlyOnceWith(MELT);
  });

  it("closes on Escape, giving focus back to its button", async () => {
    renderMenu();
    await open();

    await userEvent.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
    expect(screen.getByRole("button", { name: "More actions for Melt" })).toHaveFocus();
  });
});
