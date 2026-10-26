import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_BINDINGS, saveBindings } from "../shortcuts";
import { ShortcutList } from "./ShortcutList";

afterEach(() => {
  saveBindings(DEFAULT_BINDINGS);
});

describe("the list of keyboard shortcuts", () => {
  it("names each command's keys as they are now", () => {
    saveBindings({ ...DEFAULT_BINDINGS, toggle: "k" });

    render(<ShortcutList onClose={vi.fn()} />);

    const list = within(screen.getByRole("dialog", { name: "Keyboard shortcuts" }));
    expect(list.getByText("Play or pause").nextElementSibling).toHaveTextContent("K");
    expect(list.getByText("Up next").nextElementSibling).toHaveTextContent("Q");
  });

  it("leads to Settings to change them, closing as it goes", async () => {
    const onClose = vi.fn();
    render(<ShortcutList onClose={onClose} />);

    const link = screen.getByRole("link", { name: "Change them in Settings" });
    await userEvent.click(link);

    expect(link).toHaveAttribute("href", "#/settings");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<ShortcutList onClose={onClose} />);

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledOnce();
  });
});
