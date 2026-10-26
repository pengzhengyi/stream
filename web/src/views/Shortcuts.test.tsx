import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_BINDINGS, rebind, saveBindings } from "../shortcuts";
import { type ShortcutHandlers, Shortcuts } from "./Shortcuts";

/** A handler for every command, each one a spy. */
function spies() {
  return {
    toggle: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    previous: vi.fn(),
    next: vi.fn(),
    volumeDown: vi.fn(),
    volumeUp: vi.fn(),
    shuffle: vi.fn(),
    repeat: vi.fn(),
    favorite: vi.fn(),
    search: vi.fn(),
    queue: vi.fn(),
    help: vi.fn(),
  } satisfies ShortcutHandlers;
}

/** The shortcuts listening on a page holding `page`. */
function listening(page?: ReactNode) {
  const on = spies();
  render(
    <>
      <Shortcuts on={on} />
      {page}
    </>,
  );
  return on;
}

afterEach(() => {
  saveBindings(DEFAULT_BINDINGS);
  localStorage.clear();
});

describe("the keyboard shortcuts", () => {
  it("play or pause with Space", async () => {
    const on = listening();

    await userEvent.keyboard(" ");

    expect(on.toggle).toHaveBeenCalledOnce();
  });

  it("keep Space from scrolling the page when it plays or pauses", () => {
    listening();

    const scrolled = fireEvent.keyDown(document.body, { code: "Space", key: " " });

    expect(scrolled).toBe(false);
  });

  it("tell a key from the same key with Shift", async () => {
    const on = listening();

    await userEvent.keyboard("{Shift>}{ArrowRight}{/Shift}");

    expect(on.next).toHaveBeenCalledOnce();
    expect(on.forward).not.toHaveBeenCalled();
  });

  it("leave a key held with Ctrl or ⌘ to the browser", async () => {
    const on = listening();

    await userEvent.keyboard("{Meta>}l{/Meta}{Control>}s{/Control}l");

    expect(on.favorite).toHaveBeenCalledOnce();
    expect(on.shuffle).not.toHaveBeenCalled();
  });

  it("play or pause once while Space is held", () => {
    const on = listening();

    fireEvent.keyDown(document.body, { code: "Space", key: " " });
    fireEvent.keyDown(document.body, { code: "Space", key: " ", repeat: true });

    expect(on.toggle).toHaveBeenCalledOnce();
  });

  it("go on seeking while an arrow is held", () => {
    const on = listening();

    fireEvent.keyDown(document.body, { code: "ArrowRight", key: "ArrowRight" });
    fireEvent.keyDown(document.body, { code: "ArrowRight", key: "ArrowRight", repeat: true });

    expect(on.forward).toHaveBeenCalledTimes(2);
  });

  it("leave Space to a focused button, which it presses", async () => {
    const pressed = vi.fn();
    const on = listening(
      <button type="button" onClick={pressed}>
        Next
      </button>,
    );
    screen.getByRole("button", { name: "Next" }).focus();

    await userEvent.keyboard(" ");

    expect(pressed).toHaveBeenCalledOnce();
    expect(on.toggle).not.toHaveBeenCalled();
  });

  it("play or pause with Space after a button is clicked, rather than click it again", async () => {
    const pressed = vi.fn();
    const on = listening(
      <button type="button" onClick={pressed}>
        Alpha
      </button>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Alpha" }));

    await userEvent.keyboard(" ");

    expect(on.toggle).toHaveBeenCalledOnce();
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("leave the arrows to a focused slider, but still play or pause with Space", async () => {
    const on = listening(<input type="range" aria-label="Volume" />);
    screen.getByRole("slider", { name: "Volume" }).focus();

    await userEvent.keyboard("{ArrowRight} ");

    expect(on.forward).not.toHaveBeenCalled();
    expect(on.toggle).toHaveBeenCalledOnce();
  });

  it("leave typing to a text box", async () => {
    const on = listening(<input type="search" aria-label="Search" />);

    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "s /");

    expect(on.shuffle).not.toHaveBeenCalled();
    expect(on.toggle).not.toHaveBeenCalled();
    expect(on.search).not.toHaveBeenCalled();
  });

  it("leave every key to an open dialog", async () => {
    const on = listening(<dialog open>Add to playlists</dialog>);

    await userEvent.keyboard(" s");

    expect(on.toggle).not.toHaveBeenCalled();
    expect(on.shuffle).not.toHaveBeenCalled();
  });

  it("leave every key to an open menu", async () => {
    const on = listening(
      <div role="menu">
        <div role="menuitem" tabIndex={-1}>
          Go to artist
        </div>
      </div>,
    );
    screen.getByRole("menuitem", { name: "Go to artist" }).focus();

    await userEvent.keyboard("s");

    expect(on.shuffle).not.toHaveBeenCalled();
  });

  it("follow a command moved to other keys", async () => {
    const on = listening();
    const moved = rebind(DEFAULT_BINDINGS, "toggle", "k");
    if (!("bindings" in moved)) {
      throw new Error("k should be free");
    }

    saveBindings(moved.bindings);
    await userEvent.keyboard("k ");

    expect(on.toggle).toHaveBeenCalledOnce();
  });
});
