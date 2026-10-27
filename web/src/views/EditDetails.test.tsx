import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type Details } from "../api";
import { detailsOf, trackOf } from "../testing/server";
import { EditDetails } from "./EditDetails";

const ALBUM_FILE = trackOf(7, "ケビョウニンゲン");

async function renderDialog(
  details: Details = detailsOf(7),
  onSave = vi.fn(() => Promise.resolve()),
) {
  const onClose = vi.fn();
  render(
    <EditDetails
      track={ALBUM_FILE}
      load={() => Promise.resolve(details)}
      onSave={onSave}
      onClose={onClose}
    />,
  );
  const dialog = screen.getByRole("dialog", { name: "Edit details" });
  await within(dialog).findByRole("textbox", { name: "Title" });
  return { dialog, onSave, onClose };
}

describe("editing a song's details", () => {
  it("shows each detail's value and where it came from", async () => {
    const { dialog } = await renderDialog();

    const title = within(dialog).getByRole("textbox", { name: "Title" });

    expect(title).toHaveValue("ケビョウニンゲン");
    expect(title).toHaveAccessibleDescription("From the video");
    expect(within(dialog).getByRole("textbox", { name: "Album" })).toHaveValue("");
  });

  it("saves only the details changed from what was found", async () => {
    const { dialog, onSave, onClose } = await renderDialog();

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Album" }), "Re:Start");
    await userEvent.type(within(dialog).getByRole("spinbutton", { name: "Year" }), "2014");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ album: "Re:Start", year: 2014 });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("offers what other origins say, and saves the one chosen as the household's", async () => {
    const { dialog, onSave } = await renderDialog();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Use “BV1dm4y1s7ak”, from the file's name" }),
    );
    const title = within(dialog).getByRole("textbox", { name: "Title" });
    expect(title).toHaveValue("BV1dm4y1s7ak");
    expect(title).toHaveAccessibleDescription("Yours");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ title: "BV1dm4y1s7ak" });
  });

  it("drops the household's value when the value found is chosen again", async () => {
    const { dialog, onSave } = await renderDialog(detailsOf(7, { title: "Sick Human" }));

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Use “ケビョウニンゲン”, from the video" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith({});
  });

  it("says why the server refused, and stays open", async () => {
    const refuse = vi.fn(() => Promise.reject(new ApiError(404, "There is no Track 7.")));
    const { dialog, onClose } = await renderDialog(detailsOf(7), refuse);

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Album" }), "Re:Start");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("There is no Track 7.");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("is dismissed with Cancel, saving nothing", async () => {
    const { dialog, onSave, onClose } = await renderDialog();

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Artist" }), " feat. Hatsune");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
