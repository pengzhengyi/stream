import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_BINDINGS, loadBindings, saveBindings } from "../shortcuts";
import { ShortcutSettings } from "./ShortcutSettings";

afterEach(() => {
  saveBindings(DEFAULT_BINDINGS);
  localStorage.clear();
});

/** The keys a command's row shows. */
const keysShownFor = (name: string) =>
  within(screen.getByText(name).closest("li") ?? document.body).getByText(/./, {
    selector: "kbd",
  }).textContent;

describe("changing the keyboard shortcuts", () => {
  it("shows each command with its keys", () => {
    render(<ShortcutSettings />);

    expect(keysShownFor("Play or pause")).toBe("Space");
    expect(keysShownFor("Next")).toBe("Shift + →");
  });

  it("gives a command the next keys pressed, and keeps them in this browser", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Play or pause" }));
    await userEvent.keyboard("{Shift>}k{/Shift}");

    expect(keysShownFor("Play or pause")).toBe("Shift + K");
    expect(screen.getByRole("status")).toHaveTextContent("Play or pause is now Shift + K.");
    expect(loadBindings().toggle).toBe("shift+k");
  });

  it("waits for a key while only a modifier is held", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Shuffle" }));
    await userEvent.keyboard("{Shift>}");

    expect(screen.getByRole("button", { name: "Press new keys for Shuffle" })).toBeInTheDocument();
  });

  it("refuses keys another command has, naming it, and waits for others", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Shuffle" }));
    await userEvent.keyboard(" ");

    expect(screen.getByRole("status")).toHaveTextContent("Space is already Play or pause.");
    expect(keysShownFor("Shuffle")).toBe("S");
    expect(screen.getByRole("button", { name: "Press new keys for Shuffle" })).toHaveFocus();
  });

  it("keeps the keys a command had on Escape", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Shuffle" }));
    await userEvent.keyboard("{Escape}");

    expect(keysShownFor("Shuffle")).toBe("S");
    expect(screen.getByRole("button", { name: "Change keys for Shuffle" })).toBeInTheDocument();
  });

  it("keeps the keys a command had on moving away", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Shuffle" }));
    await userEvent.tab();
    await userEvent.tab({ shift: true });
    await userEvent.keyboard("k");

    expect(keysShownFor("Shuffle")).toBe("S");
    expect(screen.getByRole("button", { name: "Change keys for Shuffle" })).toHaveFocus();
  });

  it("refuses keys the browser keeps, and waits for others", async () => {
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Change keys for Shuffle" }));
    await userEvent.keyboard("{Meta>}w{/Meta}");

    expect(screen.getByRole("status")).toHaveTextContent("The browser keeps ⌘ + W.");
    expect(screen.getByRole("button", { name: "Press new keys for Shuffle" })).toBeInTheDocument();
  });

  it("puts every command back on its usual keys", async () => {
    saveBindings({ ...DEFAULT_BINDINGS, toggle: "k" });
    render(<ShortcutSettings />);

    await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));

    expect(keysShownFor("Play or pause")).toBe("Space");
    expect(screen.getByRole("button", { name: "Reset to defaults" })).toBeDisabled();
  });
});
