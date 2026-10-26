import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { openWithShortcuts } from "../testing/server";
import { ShortcutList } from "./ShortcutList";

describe("the list of keyboard shortcuts", () => {
  it("names each command's keys as they are now", async () => {
    await openWithShortcuts({ toggle: ["j"], mute: [] });

    render(<ShortcutList onClose={vi.fn()} />);

    const list = within(screen.getByRole("dialog", { name: "Keyboard shortcuts" }));
    expect(list.getByText("Play or pause").nextElementSibling).toHaveTextContent(/^J$/);
    expect(list.getByText("Next").nextElementSibling).toHaveTextContent("Shift + →");
    expect(list.getByText("Mute or unmute").nextElementSibling).toHaveTextContent("None");
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
