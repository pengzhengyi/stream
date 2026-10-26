import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Playlist } from "../api";
import { favoritesPlaylistOf, playlistOf, trackOf } from "../testing/server";
import { AddToPlaylist } from "./AddToPlaylist";

const OUTRO = trackOf(2, "Outro");

/**
 * The Account's Playlists: Favorites, which the server keeps; Mornings, which
 * already holds Outro; Car and Gym, which don't; and Loud, a smart playlist.
 */
const PLAYLISTS: readonly Playlist[] = [
  favoritesPlaylistOf([2]),
  playlistOf("p1", "Mornings", [1, 2]),
  playlistOf("p2", "Car", []),
  playlistOf("p3", "Gym", [1]),
  { ...playlistOf("p4", "Loud", []), rules: { version: 1, match: "all", conditions: [] } },
];

function renderDialog(onSave = vi.fn(() => Promise.resolve())) {
  const onClose = vi.fn();
  render(<AddToPlaylist track={OUTRO} playlists={PLAYLISTS} onSave={onSave} onClose={onClose} />);
  return {
    onSave,
    onClose,
    dialog: screen.getByRole("dialog", { name: "Add “Outro” to playlists" }),
  };
}

describe("adding a song to playlists", () => {
  it("offers the Account's own plain Playlists, and shows those that already hold the song", () => {
    const { dialog } = renderDialog();

    const boxes = within(dialog).getAllByRole("checkbox");

    expect(boxes.map((box) => box.closest("label")?.textContent)).toEqual([
      "MorningsAlready added",
      "Car0 songs",
      "Gym1 song",
    ]);
    expect(within(dialog).getByRole("checkbox", { name: /Mornings/ })).toBeDisabled();
    expect(within(dialog).getByRole("checkbox", { name: /Mornings/ })).toBeChecked();
  });

  it("adds the song to every Playlist chosen at once", async () => {
    const { dialog, onSave, onClose } = renderDialog();

    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Car/ }));
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Gym/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Add to 2 playlists" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith(["p2", "p3"], []);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("makes a new Playlist, chosen at once, only when the song is added", async () => {
    const { dialog, onSave } = renderDialog();

    await userEvent.type(
      within(dialog).getByRole("textbox", { name: "New playlist" }),
      "Beach{Enter}",
    );

    expect(within(dialog).getByRole("checkbox", { name: /Beach/ })).toBeChecked();
    expect(onSave).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Add to 1 playlist" }));
    expect(onSave).toHaveBeenCalledExactlyOnceWith([], ["Beach"]);
  });

  it("can't add before a Playlist is chosen", () => {
    const { dialog } = renderDialog();

    expect(within(dialog).getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("stays open and says why when the server refuses", async () => {
    const onSave = vi.fn(() => Promise.reject(new Error("The server is busy.")));
    const { dialog, onClose } = renderDialog(onSave);

    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Car/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Add to 1 playlist" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The server is busy.");
    expect(onClose).not.toHaveBeenCalled();
  });

  it.each([
    [
      "Cancel",
      async (dialog: HTMLElement) => {
        await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
      },
    ],
    [
      "Escape",
      async () => {
        await userEvent.keyboard("{Escape}");
      },
    ],
  ])("is dismissed with %s, adding nothing", async (_, dismiss) => {
    const { dialog, onSave, onClose } = renderDialog();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /Car/ }));

    await dismiss(dialog);

    expect(onClose).toHaveBeenCalledOnce();
    expect(onSave).not.toHaveBeenCalled();
  });
});
