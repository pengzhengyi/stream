import { afterEach, describe, expect, it } from "vitest";

import {
  DEFAULT_BINDINGS,
  ariaKeysOf,
  bindingOf,
  hintOf,
  labelOf,
  loadBindings,
  rebind,
  saveBindings,
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

  it("fall back to the defaults when two commands were saved with the same keys", () => {
    localStorage.setItem("medleyplay.shortcuts.v1", JSON.stringify({ next: "space" }));

    expect(loadBindings()).toEqual(DEFAULT_BINDINGS);
  });
});
