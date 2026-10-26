import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type Bindings,
  DEFAULT_BINDINGS,
  MAX_KEYS,
  addKeys,
  ariaKeysOf,
  belongsToBrowser,
  bindingOf,
  bindingsOf,
  changesOf,
  hintOf,
  labelOf,
  labelsOf,
  openAccount,
  removeKeys,
  saveBindings,
  setLayoutForTests,
  useBindings,
} from "./shortcuts";
import { serve } from "./testing/server";

const pressed = (code: string, change: Partial<KeyboardEventInit> = {}) =>
  new KeyboardEvent("keydown", { code, ...change });

/** Where this browser keeps its copy of Alice's shortcuts. */
const ALICES_COPY = "medleyplay.shortcuts.v2.1";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

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

  it("names a key as this keyboard prints it, where the browser says", () => {
    // A French keyboard prints A where a US one prints Q, and ! where it prints /.
    setLayoutForTests(
      new Map([
        ["KeyQ", "a"],
        ["Slash", "!"],
      ]),
    );

    expect([labelOf("q"), labelOf("shift+slash"), labelOf("space")]).toEqual([
      "A",
      "Shift + !",
      "Space",
    ]);
  });

  it("joins a command's keys with or, and says when it has none", () => {
    expect([labelsOf(["space", "k"]), labelsOf([])]).toEqual(["Space or K", "None"]);
  });
});

describe("a control's hint", () => {
  it("names every key of its command on hover and to assistive technology", () => {
    expect(hintOf("Play", ["space", "k"])).toEqual({
      title: "Play (Space or K)",
      "aria-keyshortcuts": "Space K",
    });
  });

  it("is only the control's name when its command has no keys", () => {
    expect(hintOf("Play", [])).toEqual({ title: "Play" });
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

describe("changing a command's keys", () => {
  it("adds keys after the ones it has", () => {
    expect(addKeys(DEFAULT_BINDINGS, "next", "n")).toEqual({
      bindings: { ...DEFAULT_BINDINGS, next: ["shift+right", "n"] },
    });
  });

  it("refuses keys another command has, naming it", () => {
    expect(addKeys(DEFAULT_BINDINGS, "next", "space")).toEqual({ taken: "toggle" });
  });

  it("changes nothing for keys the command already has", () => {
    expect(addKeys(DEFAULT_BINDINGS, "toggle", "k")).toEqual({ bindings: DEFAULT_BINDINGS });
  });

  it(`refuses a key past ${String(MAX_KEYS)}`, () => {
    const four: Bindings = { ...DEFAULT_BINDINGS, next: ["n", "o", "p", "u"] };

    expect(addKeys(four, "next", "j")).toEqual({ full: true });
  });

  it("removes one of a command's keys, leaving the others", () => {
    expect(removeKeys(DEFAULT_BINDINGS, "toggle", "space").toggle).toEqual(["k"]);
  });
});

describe("the shortcuts the server keeps", () => {
  it("are none while every command is on its defaults", () => {
    expect(changesOf(DEFAULT_BINDINGS)).toBeNull();
  });

  it("are the commands changed from the defaults, with all their keys", () => {
    const changed = removeKeys(DEFAULT_BINDINGS, "toggle", "k");

    expect(changesOf(changed)).toEqual({ toggle: ["space"] });
  });

  it("give each saved command its keys and every other its defaults", () => {
    expect(bindingsOf({ next: ["n"], mute: [] })).toEqual({
      ...DEFAULT_BINDINGS,
      next: ["n"],
      mute: [],
    });
  });

  it.each([
    ["nothing", null],
    ["not an object", ["space"]],
  ])("are the defaults when they are %s", (_, saved) => {
    expect(bindingsOf(saved)).toEqual(DEFAULT_BINDINGS);
  });

  it("drop a command that no longer exists, and keys that aren't keys", () => {
    expect(bindingsOf({ dance: ["d"], next: ["n", 4, "", "n"], shuffle: "x" })).toEqual({
      ...DEFAULT_BINDINGS,
      next: ["n"],
    });
  });

  it("put a command saved on another's keys back on its default, keeping the rest", () => {
    expect(bindingsOf({ next: ["space"], shuffle: ["x"] })).toEqual({
      ...DEFAULT_BINDINGS,
      shuffle: ["x"],
    });
  });

  it("put back each command whose default the first one put back now clashes with", () => {
    expect(bindingsOf({ next: ["space"], previous: ["shift+right"], shuffle: ["x"] })).toEqual({
      ...DEFAULT_BINDINGS,
      shuffle: ["x"],
    });
  });
});

describe("an Account's shortcuts", () => {
  it("are the ones it saved, once the server answers", async () => {
    serve({ "GET /api/me/preferences": { body: { shortcuts: { toggle: ["j"] }, revision: 3 } } });
    const { result } = renderHook(() => useBindings());

    await act(() => openAccount(1));

    expect(result.current.toggle).toEqual(["j"]);
  });

  it("are this browser's copy until the server answers", async () => {
    localStorage.setItem(ALICES_COPY, JSON.stringify({ shortcuts: { toggle: ["j"] } }));
    serve({ "GET /api/me/preferences": { status: 503 } });
    const { result } = renderHook(() => useBindings());

    await act(() => openAccount(1).catch(() => undefined));

    expect(result.current.toggle).toEqual(["j"]);
  });

  it("aren't another Account's, kept in the same browser", async () => {
    localStorage.setItem(ALICES_COPY, JSON.stringify({ shortcuts: { toggle: ["j"] } }));
    serve({ "GET /api/me/preferences": { status: 503 } });
    const { result } = renderHook(() => useBindings());

    await act(() => openAccount(1).catch(() => undefined));
    await act(() => openAccount(2).catch(() => undefined));

    expect(result.current.toggle).toEqual(DEFAULT_BINDINGS.toggle);
  });

  it("are saved with the server at the revision read, as the commands changed", async () => {
    const saved: unknown[] = [];
    serve({
      "GET /api/me/preferences": { body: { shortcuts: null, revision: 3 } },
      "PUT /api/me/preferences": (body) => {
        saved.push(body);
        return { body: { ...(body as object), revision: 4 } };
      },
    });
    await openAccount(1);

    await saveBindings({ ...DEFAULT_BINDINGS, mute: ["u"] });

    expect(saved).toEqual([{ shortcuts: { mute: ["u"] }, revision: 3 }]);
    expect(JSON.parse(localStorage.getItem(ALICES_COPY) ?? "null")).toEqual({
      shortcuts: { mute: ["u"] },
    });
  });

  it("replace ones saved elsewhere since, as the last chosen", async () => {
    const revisions: number[] = [];
    let latest = 3;
    serve({
      "GET /api/me/preferences": () => ({ body: { shortcuts: null, revision: latest } }),
      "PUT /api/me/preferences": (body) => {
        const { revision } = body as { revision: number };
        revisions.push(revision);
        return revision === latest
          ? { body: { ...(body as object), revision: latest + 1 } }
          : { status: 409, body: { detail: "Saved since." } };
      },
    });
    await openAccount(1);
    latest = 5;

    await saveBindings({ ...DEFAULT_BINDINGS, mute: ["u"] });

    expect(revisions).toEqual([3, 5]);
  });

  it("follow a change another tab of this browser kept", async () => {
    serve({ "GET /api/me/preferences": { body: { shortcuts: null, revision: 1 } } });
    const { result } = renderHook(() => useBindings());
    await act(() => openAccount(1));

    localStorage.setItem(ALICES_COPY, JSON.stringify({ shortcuts: { toggle: ["j"] } }));
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: ALICES_COPY }));
    });

    expect(result.current.toggle).toEqual(["j"]);
  });
});
