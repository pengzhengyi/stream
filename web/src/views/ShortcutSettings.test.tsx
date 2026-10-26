import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { openWithShortcuts, preferencesOf, serve } from "../testing/server";
import { ShortcutSettings } from "./ShortcutSettings";

/** The keys a command's row shows, as people read them. */
const keysShownFor = (name: string) =>
  within(screen.getByText(name).closest("li") ?? document.body)
    .queryAllByText(/./, { selector: "kbd" })
    .map((kbd) => kbd.textContent);

/** Render the section over a server keeping what it saves; return what it was sent. */
function renderSaving() {
  const { calls } = serve(preferencesOf());
  render(<ShortcutSettings />);
  return calls;
}

describe("changing the keyboard shortcuts", () => {
  it("shows each command with its keys", () => {
    renderSaving();

    expect(keysShownFor("Play or pause")).toEqual(["Space", "K"]);
    expect(keysShownFor("Next")).toEqual(["Shift + →"]);
  });

  it("adds the next keys pressed to a command, and saves them with the Account", async () => {
    const calls = renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Next" }));
    await userEvent.keyboard("{Shift>}n{/Shift}");

    expect(keysShownFor("Next")).toEqual(["Shift + →", "Shift + N"]);
    expect(screen.getByRole("status")).toHaveTextContent("Next now also has Shift + N.");
    await waitFor(() => {
      expect(calls).toContain("PUT /api/me/preferences");
    });
  });

  it("removes one of a command's keys, keeping the others", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Remove K from Play or pause" }));

    expect(keysShownFor("Play or pause")).toEqual(["Space"]);
    expect(screen.getByRole("status")).toHaveTextContent("Play or pause no longer has K.");
  });

  it("says a command with no keys has none", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Remove M from Mute or unmute" }));

    expect(
      within(screen.getByText("Mute or unmute").closest("li") ?? document.body).getByText("None"),
    ).toBeInTheDocument();
  });

  it("waits for a key while only a modifier is held", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Shuffle" }));
    await userEvent.keyboard("{Shift>}");

    expect(
      screen.getByRole("button", { name: "Press keys to add to Shuffle" }),
    ).toBeInTheDocument();
  });

  it("refuses keys another command has, naming it, and waits for others", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Shuffle" }));
    await userEvent.keyboard(" ");

    expect(screen.getByRole("status")).toHaveTextContent("Space is already Play or pause.");
    expect(keysShownFor("Shuffle")).toEqual(["S"]);
    expect(screen.getByRole("button", { name: "Press keys to add to Shuffle" })).toHaveFocus();
  });

  it("refuses keys the browser keeps, and waits for others", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Shuffle" }));
    await userEvent.keyboard("{Meta>}w{/Meta}");

    expect(screen.getByRole("status")).toHaveTextContent("The browser keeps ⌘ + W.");
    expect(
      screen.getByRole("button", { name: "Press keys to add to Shuffle" }),
    ).toBeInTheDocument();
  });

  it("adds nothing on Escape", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Shuffle" }));
    await userEvent.keyboard("{Escape}");

    expect(keysShownFor("Shuffle")).toEqual(["S"]);
    expect(screen.getByRole("button", { name: "Add keys to Shuffle" })).toBeInTheDocument();
  });

  it("adds nothing on moving away", async () => {
    renderSaving();

    await userEvent.click(screen.getByRole("button", { name: "Add keys to Shuffle" }));
    await userEvent.tab();
    await userEvent.tab({ shift: true });
    await userEvent.keyboard("j");

    expect(keysShownFor("Shuffle")).toEqual(["S"]);
    expect(screen.getByRole("button", { name: "Add keys to Shuffle" })).toHaveFocus();
  });

  it("says when the server didn't keep a change, which the page still uses", async () => {
    serve({ "PUT /api/me/preferences": { status: 503, body: { detail: "Busy" } } });
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Remove K from Play or pause" }));

    expect(await screen.findByText(/The server didn't keep them/)).toBeInTheDocument();
    expect(keysShownFor("Play or pause")).toEqual(["Space"]);
  });

  it("puts every command back on its usual keys", async () => {
    await openWithShortcuts({ toggle: ["j"] });
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));

    expect(keysShownFor("Play or pause")).toEqual(["Space", "K"]);
    expect(screen.getByRole("button", { name: "Reset to defaults" })).toBeDisabled();
  });
});
