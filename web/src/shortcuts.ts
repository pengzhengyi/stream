/**
 * @file The keyboard shortcuts: each command, the keys bound to it, and where they are kept.
 *
 * A binding is written as react-hotkeys-hook reads it: modifiers, then a physical
 * key, joined by `+`, such as `shift+right` or `slash`. Physical keys work the
 * same on any keyboard layout. The bindings are this browser's own, so they live
 * in `localStorage`, and every part of the page reads the same ones.
 */

// cspell:ignore backquote bracketleft bracketright

import { useSyncExternalStore } from "react";

/** Something a shortcut does. */
export type Command =
  | "toggle"
  | "back"
  | "forward"
  | "previous"
  | "next"
  | "volumeDown"
  | "volumeUp"
  | "shuffle"
  | "repeat"
  | "favorite"
  | "search"
  | "queue"
  | "help";

/** Each command's keys. */
export type Bindings = Readonly<Record<Command, string>>;

/** The commands in the order Settings and the list of shortcuts show them, with their names. */
export const COMMANDS: readonly { readonly command: Command; readonly name: string }[] = [
  { command: "toggle", name: "Play or pause" },
  { command: "back", name: "Back 5 seconds" },
  { command: "forward", name: "Ahead 5 seconds" },
  { command: "previous", name: "Previous" },
  { command: "next", name: "Next" },
  { command: "volumeDown", name: "Volume down" },
  { command: "volumeUp", name: "Volume up" },
  { command: "shuffle", name: "Shuffle" },
  { command: "repeat", name: "Repeat" },
  { command: "favorite", name: "Favorite the song playing" },
  { command: "search", name: "Search" },
  { command: "queue", name: "Up next" },
  { command: "help", name: "Keyboard shortcuts" },
];

export const DEFAULT_BINDINGS: Bindings = {
  toggle: "space",
  back: "left",
  forward: "right",
  previous: "shift+left",
  next: "shift+right",
  volumeDown: "minus",
  volumeUp: "equal",
  shuffle: "s",
  repeat: "r",
  favorite: "l",
  search: "slash",
  queue: "q",
  help: "shift+slash",
};

const KEY = "medleyplay.shortcuts.v1";
const MODIFIERS = ["ctrl", "alt", "shift", "meta"] as const;
const MODIFIER_NAMES: Readonly<Record<string, readonly [label: string, aria: string]>> = {
  ctrl: ["Ctrl", "Control"],
  alt: ["Alt", "Alt"],
  shift: ["Shift", "Shift"],
  meta: ["⌘", "Meta"],
};
/** Keys whose names read better as symbols, for people and for assistive technology. */
const KEY_NAMES: Readonly<Record<string, readonly [label: string, aria: string]>> = {
  space: ["Space", "Space"],
  left: ["←", "ArrowLeft"],
  right: ["→", "ArrowRight"],
  up: ["↑", "ArrowUp"],
  down: ["↓", "ArrowDown"],
  minus: ["-", "-"],
  equal: ["=", "="],
  slash: ["/", "/"],
  backslash: ["\\", "\\"],
  comma: [",", ","],
  period: [".", "."],
  semicolon: [";", ";"],
  quote: ["'", "'"],
  backquote: ["`", "`"],
  bracketleft: ["[", "["],
  bracketright: ["]", "]"],
  enter: ["Enter", "Enter"],
  backspace: ["Backspace", "Backspace"],
};
/** Keys that are only ever part of a shortcut, or that the page needs for itself. */
const NOT_ALONE = new Set(["Escape", "Tab"]);

/** Return `keys` as people read them, such as `Shift + →`. */
export function labelOf(keys: string): string {
  return keys
    .split("+")
    .map((part) => MODIFIER_NAMES[part]?.[0] ?? KEY_NAMES[part]?.[0] ?? part.toUpperCase())
    .join(" + ");
}

/** Return `keys` as `aria-keyshortcuts` writes them, such as `Shift+ArrowRight`. */
export function ariaKeysOf(keys: string): string {
  return keys
    .split("+")
    .map((part) => MODIFIER_NAMES[part]?.[1] ?? KEY_NAMES[part]?.[1] ?? part.toUpperCase())
    .join("+");
}

/** Return the hover text and `aria-keyshortcuts` for a control named `name`, on `keys`. */
export function hintOf(
  name: string,
  keys: string,
): { readonly title: string; readonly "aria-keyshortcuts": string } {
  return { title: `${name} (${labelOf(keys)})`, "aria-keyshortcuts": ariaKeysOf(keys) };
}

/** Return the binding a key press would be, or `undefined` for a press that can't be one. */
export function bindingOf(event: KeyboardEvent): string | undefined {
  const key = keyOf(event.code);
  if (key === undefined) {
    return undefined;
  }
  const held = {
    ctrl: event.ctrlKey,
    alt: event.altKey,
    shift: event.shiftKey,
    meta: event.metaKey,
  };
  return [...MODIFIERS.filter((modifier) => held[modifier]), key].join("+");
}

/**
 * Return the name of the physical key `code`, or `undefined` for a modifier or a key kept.
 *
 * Names are react-hotkeys-hook's, so the same key has one name: `KeyA` is `a`,
 * and `Digit1` and `Numpad1` are both `1`, as the hook treats them alike.
 */
function keyOf(code: string): string | undefined {
  if (NOT_ALONE.has(code) || /^(Shift|Control|Alt|Meta|OS)(Left|Right)?$/.test(code)) {
    return undefined;
  }
  const arrow = /^Arrow(Left|Right|Up|Down)$/.exec(code);
  if (arrow !== null) {
    return arrow[1]?.toLowerCase();
  }
  return code.toLowerCase().replace(/key|digit|numpad/, "");
}

/** Keys the browser or the system keeps, which a page never sees or shouldn't take. */
const BROWSERS = new Set(["f5", "f11", "f12"]);
const BROWSER_LETTERS = new Set(["l", "n", "q", "r", "t", "w"]);

/** Whether the browser or the system keeps `keys`, such as ⌘ + W, which closes the tab. */
export function belongsToBrowser(keys: string): boolean {
  const parts = keys.split("+");
  const key = parts.at(-1) ?? "";
  const held = parts.includes("ctrl") || parts.includes("meta");
  return BROWSERS.has(key) || (held && BROWSER_LETTERS.has(key));
}

/** Return `bindings` with `command` on `keys`, or the command that already has them. */
export function rebind(
  bindings: Bindings,
  command: Command,
  keys: string,
): { readonly bindings: Bindings } | { readonly taken: Command } {
  const taken = COMMANDS.find(
    (each) => each.command !== command && bindings[each.command] === keys,
  );
  return taken === undefined
    ? { bindings: { ...bindings, [command]: keys } }
    : { taken: taken.command };
}

/** Return the bindings this browser kept, each command on its default where none was. */
export function loadBindings(): Bindings {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (typeof saved !== "object" || saved === null || Array.isArray(saved)) {
      return DEFAULT_BINDINGS;
    }
    const kept = new Map(
      Object.entries(saved).filter(
        (entry): entry is [Command, string] =>
          entry[0] in DEFAULT_BINDINGS && typeof entry[1] === "string" && entry[1] !== "",
      ),
    );
    // Two commands on the same keys would leave one unreachable, as when a new
    // command's default is keys already saved for another. A saved command that
    // shares keys goes back to its default, until no two share.
    for (;;) {
      const bindings: Bindings = { ...DEFAULT_BINDINGS, ...Object.fromEntries(kept) };
      const clashing = [...kept.keys()].filter((command) =>
        COMMANDS.some(
          (other) => other.command !== command && bindings[other.command] === bindings[command],
        ),
      );
      if (clashing.length === 0) {
        return bindings;
      }
      for (const command of clashing) {
        kept.delete(command);
      }
    }
  } catch {
    return DEFAULT_BINDINGS;
  }
}

/** Keep `bindings` for this browser, and tell every part of the page that reads them. */
export function saveBindings(bindings: Bindings): void {
  shown = bindings;
  for (const listener of listeners) {
    listener();
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(bindings));
  } catch {
    // A browser that keeps nothing still uses them until the page closes.
  }
}

let shown: Bindings | undefined;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  // Another tab that changes them says so here.
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) {
      shown = loadBindings();
      listener();
    }
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

const current = () => (shown ??= loadBindings());

/** The bindings in use; every part of the page reads the same ones. */
export function useBindings(): Bindings {
  return useSyncExternalStore(subscribe, current);
}
