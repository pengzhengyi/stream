import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type Song, type SongRowIn, type Songs } from "../api";
import { splitSongsOf, trackOf } from "../testing/server";
import { EditSongs } from "./EditSongs";

/** *Bremen*, a whole album uploaded as one video. */
const BREMEN = trackOf(104, "BV1dm4y1s7ak", { split: true });

/** *Bremen* split into three songs. */
const SPLIT = splitSongsOf(104, [
  [1, 0, "アイネクライネ"],
  [2, 252_000, "ゴーゴー幽霊船"],
  [3, 480_000, "Last"],
]);

/** The song list the video's description gives. */
const LISTED: readonly Song[] = [
  { start_ms: 0, title: "アイネクライネ", artist: "" },
  { start_ms: 252_000, title: "ゴーゴー幽霊船", artist: "ハチ" },
];

async function renderEditor(
  songs: Songs = SPLIT,
  {
    onSave = vi.fn<(rows: readonly SongRowIn[]) => Promise<void>>(() => Promise.resolve()),
    onUnsplit = vi.fn<() => Promise<void>>(() => Promise.resolve()),
    readList = vi.fn<(trackId: number, text: string) => Promise<readonly Song[]>>(() =>
      Promise.resolve(LISTED),
    ),
  } = {},
) {
  const onClose = vi.fn();
  render(
    <EditSongs
      album={BREMEN}
      load={() => Promise.resolve(songs)}
      readList={readList}
      onSave={onSave}
      onUnsplit={onUnsplit}
      onClose={onClose}
    />,
  );
  const dialog = screen.getByRole("dialog");
  await within(dialog).findByRole("button", { name: "Add a song" });
  return { dialog, onSave, onUnsplit, readList, onClose };
}

const box = (dialog: HTMLElement, name: string) => within(dialog).getByRole("textbox", { name });
const press = (dialog: HTMLElement, name: string | RegExp) =>
  userEvent.click(within(dialog).getByRole("button", { name }));

describe("editing a file's songs", () => {
  it("shows each song's start, title, and artist", async () => {
    const { dialog } = await renderEditor();

    expect(dialog).toHaveAccessibleName("Edit songs");
    expect(box(dialog, "Start of song 2")).toHaveValue("4:12");
    expect(box(dialog, "Title of song 2")).toHaveValue("ゴーゴー幽霊船");
    expect(box(dialog, "Start of song 3")).toHaveValue("8:00");
  });

  it("splits a file from the list found in its video's details, as new songs", async () => {
    const { dialog, onSave, onClose } = await renderEditor(splitSongsOf(104, [], [LISTED]));

    expect(dialog).toHaveAccessibleName("Split into songs");
    await press(dialog, "Use the 2 songs from the video's details");
    await press(dialog, "Save");

    expect(onSave).toHaveBeenCalledExactlyOnceWith([
      { id: null, start_ms: 0, title: "アイネクライネ", artist: "" },
      { id: null, start_ms: 252_000, title: "ゴーゴー幽霊船", artist: "ハチ" },
    ]);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("reads a pasted list into its rows", async () => {
    const { dialog, readList } = await renderEditor(splitSongsOf(104, []));

    await userEvent.click(within(dialog).getByText("Paste a list"));
    await userEvent.click(box(dialog, "Song list"));
    await userEvent.paste("00:00 アイネクライネ\n04:12 ゴーゴー幽霊船 - ハチ");
    await press(dialog, "Read the list");

    expect(readList).toHaveBeenCalledExactlyOnceWith(
      104,
      "00:00 アイネクライネ\n04:12 ゴーゴー幽霊船 - ハチ",
    );
    expect(box(dialog, "Artist of song 2")).toHaveValue("ハチ");
  });

  it("keeps each song by its id when its row is moved and renamed", async () => {
    const { dialog, onSave } = await renderEditor();

    await press(dialog, "Move “Last” up");
    await userEvent.clear(box(dialog, "Start of song 2"));
    await userEvent.type(box(dialog, "Start of song 2"), "3:00");
    await userEvent.type(box(dialog, "Title of song 2"), " (Reprise)");
    await press(dialog, "Save");

    expect(onSave).toHaveBeenCalledExactlyOnceWith([
      { id: 1, start_ms: 0, title: "アイネクライネ", artist: "" },
      { id: 3, start_ms: 180_000, title: "Last (Reprise)", artist: "" },
      { id: 2, start_ms: 252_000, title: "ゴーゴー幽霊船", artist: "" },
    ]);
  });

  it("says what saving removes first, and saves on the second press", async () => {
    const { dialog, onSave } = await renderEditor();

    await press(dialog, "Remove “Last”");
    await press(dialog, "Save");

    expect(onSave).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "Saving removes 1 song, with their ratings and plays.",
    );
    await press(dialog, "Save and remove 1 song");
    expect(onSave).toHaveBeenCalledOnce();
  });

  it("says what unsplitting removes first, and unsplits on the second press", async () => {
    const { dialog, onUnsplit } = await renderEditor();

    await press(dialog, "Unsplit");

    expect(onUnsplit).not.toHaveBeenCalled();
    await press(dialog, "Unsplit and remove 3 songs");
    expect(onUnsplit).toHaveBeenCalledOnce();
  });

  it("says which song starts at no time, saving nothing", async () => {
    const { dialog, onSave } = await renderEditor();

    await press(dialog, "Add a song");
    await userEvent.type(box(dialog, "Start of song 4"), "8:75");
    await press(dialog, "Save");

    expect(within(dialog).getByRole("alert")).toHaveTextContent("Song 4 starts at no time");
    expect(onSave).not.toHaveBeenCalled();
  });

  it("says why the server refused, and stays open", async () => {
    const { dialog, onClose } = await renderEditor(SPLIT, {
      onSave: vi.fn(() =>
        Promise.reject(
          new ApiError(422, "Starts rise at least a second a song; song 2 breaks that."),
        ),
      ),
    });

    await press(dialog, "Save");

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("song 2 breaks that");
    expect(onClose).not.toHaveBeenCalled();
  });
});
