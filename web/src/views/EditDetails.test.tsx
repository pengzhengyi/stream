import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type Details, type VideoRead, type VideoText } from "../api";
import { ALBUM_FILE_ORIGINS, TAGGED_ORIGINS, detailsOf, trackOf } from "../testing/server";
import { EditDetails } from "./EditDetails";

const ALBUM_FILE = trackOf(7, "ケビョウニンゲン");

async function renderDialog(
  details: Details = detailsOf(7),
  onSave = vi.fn<(changes: object) => Promise<void>>(() => Promise.resolve()),
  onReadVideo = vi.fn<(text: VideoText) => Promise<VideoRead>>(() =>
    Promise.reject(new Error("No video read in this test.")),
  ),
) {
  const onClose = vi.fn();
  render(
    <EditDetails
      track={ALBUM_FILE}
      load={() => Promise.resolve(details)}
      onSave={onSave}
      onReadVideo={onReadVideo}
      onClose={onClose}
    />,
  );
  const dialog = screen.getByRole("dialog", { name: "Edit details" });
  await within(dialog).findByRole("textbox", { name: "Title" });
  return { dialog, onSave, onClose };
}

const NUMBERS = new Set(["Track", "Disc", "Year"]);

/** The box of the detail labelled `name`. */
const box = (dialog: HTMLElement, name: string) =>
  within(dialog).getByRole(NUMBERS.has(name) ? "spinbutton" : "textbox", { name });

const use = (dialog: HTMLElement, value: string, from: string) =>
  userEvent.click(within(dialog).getByRole("button", { name: `Use “${value}”, from ${from}` }));

const save = (dialog: HTMLElement) =>
  userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

describe("editing a song's details", () => {
  it("shows each detail's value and where it came from", async () => {
    const { dialog } = await renderDialog();

    expect(box(dialog, "Title")).toHaveValue("ケビョウニンゲン");
    expect(box(dialog, "Title")).toHaveAccessibleDescription("From the video");
    expect(box(dialog, "Album")).toHaveValue("");
    expect(dialog).toHaveAccessibleDescription("ケビョウニンゲン");
  });

  it("saves only the details changed", async () => {
    const { dialog, onSave, onClose } = await renderDialog();

    await userEvent.type(box(dialog, "Album"), "Re:Start");
    await userEvent.type(box(dialog, "Year"), "2014");
    await save(dialog);

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ album: "Re:Start", year: 2014 });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("offers what other origins say, and keeps the one chosen as the household's", async () => {
    const { dialog, onSave } = await renderDialog();

    await use(dialog, "BV1dm4y1s7ak", "the file's name");

    expect(box(dialog, "Title")).toHaveValue("BV1dm4y1s7ak");
    expect(box(dialog, "Title")).toHaveAccessibleDescription("Yours");
    await save(dialog);
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ title: "BV1dm4y1s7ak" });
  });

  it("drops the household's value when what would show anyway is chosen", async () => {
    const { dialog, onSave } = await renderDialog(detailsOf(7, { title: "Sick Human" }));

    await use(dialog, "ケビョウニンゲン", "the video");
    await save(dialog);

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ title: null });
  });

  it("drops a value typed back to what would show anyway", async () => {
    const { dialog, onSave } = await renderDialog();

    await userEvent.type(box(dialog, "Title"), "!{Backspace}");

    expect(box(dialog, "Title")).toHaveAccessibleDescription("From the video");
    await save(dialog);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("drops a value that reads as what would show anyway, so '03' is track 3", async () => {
    const { dialog, onSave } = await renderDialog(detailsOf(3, {}, TAGGED_ORIGINS));

    await userEvent.clear(box(dialog, "Track"));
    await userEvent.type(box(dialog, "Track"), "03");
    await userEvent.type(box(dialog, "Title"), " ");
    await save(dialog);

    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves nothing for a box emptied where nothing is found", async () => {
    const { dialog, onSave } = await renderDialog();

    await userEvent.type(box(dialog, "Genre"), "a{Backspace}");

    expect(box(dialog, "Genre")).not.toHaveAccessibleDescription("Yours");
    await save(dialog);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("closes without a request when nothing changed, keeping the household's empty text", async () => {
    const { dialog, onSave, onClose } = await renderDialog(detailsOf(7, { genre: "" }));

    await save(dialog);

    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  describe("with the album fields, which come together from one origin", () => {
    it("empties the file's track and year once the household names another album", async () => {
      const { dialog } = await renderDialog(detailsOf(3, {}, TAGGED_ORIGINS));

      await userEvent.clear(box(dialog, "Album"));
      await userEvent.type(box(dialog, "Album"), "Other");

      expect(box(dialog, "Track")).toHaveValue(null);
      expect(box(dialog, "Track")).toHaveAccessibleDescription("Hidden, as your album differs");
      expect(box(dialog, "Year")).toHaveValue(null);
    });

    it("keeps a value of the file's chosen under the household's album", async () => {
      const { dialog, onSave } = await renderDialog(detailsOf(3, {}, TAGGED_ORIGINS));

      await userEvent.clear(box(dialog, "Album"));
      await userEvent.type(box(dialog, "Album"), "Other");
      await use(dialog, "3", "the file's tags");
      await save(dialog);

      expect(onSave).toHaveBeenCalledExactlyOnceWith({ album: "Other", track_number: 3 });
    });

    it("brings the file's album fields back when its album is chosen again", async () => {
      const { dialog, onSave } = await renderDialog(
        detailsOf(3, { album: "Other" }, TAGGED_ORIGINS),
      );

      await use(dialog, "Re:Start", "the file's tags");

      expect(box(dialog, "Album artist")).toHaveValue("MAYU");
      await save(dialog);
      expect(onSave).toHaveBeenCalledExactlyOnceWith({ album: null });
    });
  });

  it("says what shows when a number of the household's is left empty", async () => {
    const { dialog, onSave } = await renderDialog(detailsOf(3, { year: 2016 }, TAGGED_ORIGINS));

    await userEvent.clear(box(dialog, "Year"));

    expect(box(dialog, "Year")).toHaveAccessibleDescription(
      "Left empty, so 2014 from the file's tags shows",
    );
    await save(dialog);
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ year: null });
  });

  it("says why the server refused, and stays open", async () => {
    const refuse = vi.fn(() => Promise.reject(new ApiError(404, "There is no Track 7.")));
    const { dialog, onClose } = await renderDialog(detailsOf(7), refuse);

    await userEvent.type(box(dialog, "Album"), "Re:Start");
    await save(dialog);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("There is no Track 7.");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("can't be cancelled while a save is under way", async () => {
    const { dialog } = await renderDialog(
      detailsOf(7),
      vi.fn(() => new Promise<void>(() => undefined)),
    );

    await userEvent.type(box(dialog, "Album"), "Re:Start");
    await save(dialog);
    await userEvent.keyboard("{Escape}");

    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(dialog).toHaveAttribute("open");
  });

  it("is dismissed with Cancel, saving nothing", async () => {
    const { dialog, onSave, onClose } = await renderDialog();

    await userEvent.type(box(dialog, "Artist"), " feat. Hatsune");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("says why the details couldn't be read, and can't be saved", async () => {
    render(
      <EditDetails
        track={ALBUM_FILE}
        load={() => Promise.reject(new ApiError(404, "There is no Track 7."))}
        onSave={vi.fn()}
        onReadVideo={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Edit details" });

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("There is no Track 7.");
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  describe("pasting the video's details", () => {
    /** An album video's title and description, as Bilibili shows them. */
    const BREMEN: VideoText = {
      title: "ハチ 全专《Bremen》",
      description: `ハチの1stアルバム
00:00 アイネクライネ
04:12 ゴーゴー幽霊船 - ハチ`,
    };

    /** What the server reads from `BREMEN`: the album, by ハチ, and its two songs. */
    const BREMEN_READ: VideoRead = {
      details: detailsOf(
        7,
        {},
        {
          video: { title: "Bremen", artist: "ハチ", album: "Bremen", album_artist: "ハチ" },
          file_name: { title: "BV1dm4y1s7ak" },
        },
        BREMEN,
      ),
      songs: [
        { start_ms: 0, title: "アイネクライネ", artist: "" },
        { start_ms: 252_000, title: "ゴーゴー幽霊船", artist: "ハチ" },
      ],
    };

    const paste = async (dialog: HTMLElement, text: VideoText) => {
      await userEvent.click(within(dialog).getByText("Paste the video's details"));
      await userEvent.click(within(dialog).getByRole("textbox", { name: "Video title" }));
      await userEvent.paste(text.title);
      await userEvent.click(within(dialog).getByRole("textbox", { name: "Description" }));
      await userEvent.paste(text.description);
    };

    const read = (dialog: HTMLElement) =>
      userEvent.click(within(dialog).getByRole("button", { name: "Read the video's details" }));

    it("reads a pasted title and description, and shows what they say", async () => {
      const onReadVideo = vi.fn(() => Promise.resolve(BREMEN_READ));
      const { dialog } = await renderDialog(detailsOf(7), undefined, onReadVideo);

      await paste(dialog, BREMEN);
      await read(dialog);

      expect(onReadVideo).toHaveBeenCalledExactlyOnceWith(BREMEN);
      expect(box(dialog, "Album")).toHaveValue("Bremen");
      expect(box(dialog, "Album")).toHaveAccessibleDescription("From the video");
      expect(within(dialog).getByRole("status")).toHaveTextContent(
        "Read the video's details. It lists 2 songs.",
      );
    });

    it("keeps what the household typed when the video's details are read", async () => {
      const { dialog } = await renderDialog(
        detailsOf(7),
        undefined,
        vi.fn(() => Promise.resolve(BREMEN_READ)),
      );

      await userEvent.clear(box(dialog, "Title"));
      await userEvent.type(box(dialog, "Title"), "Sick Human");
      await paste(dialog, BREMEN);
      await read(dialog);

      expect(box(dialog, "Title")).toHaveValue("Sick Human");
      expect(box(dialog, "Title")).toHaveAccessibleDescription("Yours");
    });

    it("opens with the video's text read before", async () => {
      const { dialog } = await renderDialog(detailsOf(7, {}, ALBUM_FILE_ORIGINS, BREMEN));

      await userEvent.click(within(dialog).getByText("Paste the video's details"));

      expect(within(dialog).getByRole("textbox", { name: "Video title" })).toHaveValue(
        BREMEN.title,
      );
      expect(within(dialog).getByRole("textbox", { name: "Description" })).toHaveValue(
        BREMEN.description,
      );
    });

    it("reads rather than saves on Enter in the video's title", async () => {
      const onSave = vi.fn(() => Promise.resolve());
      const onReadVideo = vi.fn(() => Promise.resolve(BREMEN_READ));
      const { dialog } = await renderDialog(detailsOf(7), onSave, onReadVideo);

      await paste(dialog, { title: BREMEN.title, description: "" });
      await userEvent.type(within(dialog).getByRole("textbox", { name: "Video title" }), "{Enter}");

      expect(onReadVideo).toHaveBeenCalledOnce();
      expect(onSave).not.toHaveBeenCalled();
    });

    it("says why the video's details couldn't be read", async () => {
      const { dialog } = await renderDialog(
        detailsOf(7),
        undefined,
        vi.fn(() => Promise.reject(new ApiError(422, "The description is too long."))),
      );

      await paste(dialog, BREMEN);
      await read(dialog);

      expect(await within(dialog).findByRole("alert")).toHaveTextContent(
        "The description is too long.",
      );
      expect(box(dialog, "Album")).toHaveValue("");
    });
  });
});
