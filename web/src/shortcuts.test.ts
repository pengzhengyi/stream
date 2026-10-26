import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_BINDINGS,
  ariaKeysOf,
  belongsToBrowser,
  bindingOf,
  hintOf,
  labelOf,
  loadBindings,
  rebind,
  saveBindings,
  useBindings,
} from "./shortcuts";

const pressed = (code: string, change: Partial<KeyboardEventInit> = {}) =>
  new KeyboardEvent("keydown", { code, ...change });

describe("a binding's names", () => {
  it.each([
    ["space", "Space", "Space"],
    ["shift+right", "Shift + →", "Shift+ArrowRight"],
    ["shift+slash", "Shift + /", "Shift+/"],
    ["minus", "-", "-"],
    ["equal", "=", "="],
    ["l", "L", "L"],
    ["ctrl+alt+k", "Ctrl + Alt + K", "Control+Alt+K"],
  ])("writes %s for people as %s and for assistive technology as %s", (keys, label, aria) => {
    expect([labelOf(keys), ariaKeysOf(keys)]).toEqual([label, aria]);
  });
});

describe("a control's hint", () => {
  it("names its keys on hover and to assistive technology", () => {
    expect(hintOf("Next", "shift+right")).toEqual({
      title: "Next (Shift + →)",
      "aria-keyshortcuts": "Shift+ArrowRight",
    });
  });
});

describe("recording a binding", () => {
  it.each([
    [pressed("KeyN"), "n"],
    [pressed("KeyN", { shiftKey: true }), "shift+n"],
    [pressed("Digit1", { ctrlKey: true, altKey: true }), "ctrl+alt+1"],
    [pressed("ArrowRight", { shiftKey: true }), "shift+right"],
    [pressed("Space"), "space"],
    [pressed("Slash", { shiftKey: true }), "shift+slash"],
    [pressed("Equal", { metaKey: true }), "meta+equal"],
    [pressed("Numpad1"), "1"],
    [pressed("Comma"), "comma"],
  ])("takes a key pressed as the binding it would be", (event, keys) => {
    expect(bindingOf(event)).toBe(keys);
  });

  it.each(["ShiftLeft", "ControlRight", "AltLeft", "MetaLeft", "Escape", "Tab"])(
    "waits past %s, which can't be a shortcut alone",
    (code) => {
      expect(bindingOf(pressed(code))).toBeUndefined();
    },
  );
});

describe("keys the browser keeps", () => {
  it.each(["meta+w", "ctrl+t", "meta+q", "ctrl+r", "f5", "f11", "shift+f12"])(
    "include %s",
    (keys) => {
      expect(belongsToBrowser(keys)).toBe(true);
    },
  );

  it.each(["w", "shift+w", "alt+t", "k", "meta+k"])("leave out %s", (keys) => {
    expect(belongsToBrowser(keys)).toBe(false);
  });
});

describe("changing a binding", () => {
  it("gives the command the new keys", () => {
    const changed = rebind(DEFAULT_BINDINGS, "next", "n");

    expect(changed).toEqual({ bindings: { ...DEFAULT_BINDINGS, next: "n" } });
  });

  it("refuses keys another command has, naming it", () => {
    expect(rebind(DEFAULT_BINDINGS, "next", "space")).toEqual({ taken: "toggle" });
  });

  it("takes back the keys the command already has", () => {
    expect(rebind(DEFAULT_BINDINGS, "next", DEFAULT_BINDINGS.next)).toEqual({
      bindings: DEFAULT_BINDINGS,
    });
  });
});

describe("the saved bindings", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("come back as they were saved", () => {
    saveBindings({ ...DEFAULT_BINDINGS, next: "n" });

    expect(loadBindings()).toEqual({ ...DEFAULT_BINDINGS, next: "n" });
  });

  it.each([
    ["nothing", null],
    ["unreadable", "{"],
    ["not an object", "[]"],
  ])("are the defaults when the browser kept %s", (_, saved) => {
    if (saved !== null) {
      localStorage.setItem("medleyplay.shortcuts.v1", saved);
    }

    expect(loadBindings()).toEqual(DEFAULT_BINDINGS);
  });

  it("fill a command saved before it existed, and drop one that no longer does", () => {
    localStorage.setItem(
      "medleyplay.shortcuts.v1",
      JSON.stringify({ next: "n", dance: "d", shuffle: 4 }),
    );

    expect(loadBindings()).toEqual({ ...DEFAULT_BINDINGS, next: "n" });
  });

  it("put a command saved on another's keys back on its default, keeping the rest", () => {
    localStorage.setItem(
      "medleyplay.shortcuts.v1",
      JSON.stringify({ next: "space", shuffle: "x" }),
    );

    expect(loadBindings()).toEqual({ ...DEFAULT_BINDINGS, shuffle: "x" });
  });

  it("put back each command whose default the first one put back now clashes with", () => {
    localStorage.setItem(
      "medleyplay.shortcuts.v1",
      JSON.stringify({ next: "space", previous: "shift+right", shuffle: "x" }),
    );

    expect(loadBindings()).toEqual({ ...DEFAULT_BINDINGS, shuffle: "x" });
  });

  it("follow a change another tab saved", () => {
    const changed = vi.fn();
    const { unmount } = renderHook(() => {
      changed(useBindings().toggle);
    });

    localStorage.setItem("medleyplay.shortcuts.v1", JSON.stringify({ toggle: "k" }));
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "medleyplay.shortcuts.v1" }));
    });

    expect(changed).toHaveBeenLastCalledWith("k");
    unmount();
  });
});
