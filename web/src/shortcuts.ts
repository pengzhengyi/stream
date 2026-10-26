/**
 * @file The keyboard shortcuts: each command, the keys bound to it, and where they are kept.
 *
 * A binding is written as react-hotkeys-hook reads it: modifiers, then a physical
 * key, joined by `+`, such as `shift+right` or `slash`. Physical keys work the
 * same on any keyboard layout, and a label names the key as the layout prints
 * it, where the browser says. A command has any number of bindings, none
 * included. The bindings are the Account's: the server keeps the commands
 * changed from the defaults, and this browser keeps a copy of each Account's,
 * so the page has them before the server answers.
 */

// cspell:ignore backquote bracketleft bracketright

import { useSyncExternalStore } from "react";

import { ApiError, type Preferences, api } from "./api";

/** Something a shortcut does. */
export type Command =
  | "toggle"
  | "back"
  | "forward"
  | "previous"
  | "next"
  | "volumeDown"
  | "volumeUp"
  | "mute"
  | "shuffle"
  | "repeat"
  | "favorite"
  | "search"
  | "queue"
  | "help";

/** Each command's keys. */
export type Bindings = Readonly<Record<Command, readonly string[]>>;

/** The commands changed from the defaults, as the server keeps them; `null` for none. */
export type SavedShortcuts = Readonly<Record<string, readonly string[]>> | null;

/** The commands in the order Settings and the list of shortcuts show them, with their names. */
export const COMMANDS: readonly { readonly command: Command; readonly name: string }[] = [
  { command: "toggle", name: "Play or pause" },
  { command: "back", name: "Back 5 seconds" },
  { command: "forward", name: "Ahead 5 seconds" },
  { command: "previous", name: "Previous" },
  { command: "next", name: "Next" },
  { command: "volumeDown", name: "Volume down" },
  { command: "volumeUp", name: "Volume up" },
  { command: "mute", name: "Mute or unmute" },
  { command: "shuffle", name: "Shuffle" },
  { command: "repeat", name: "Repeat" },
  { command: "favorite", name: "Favorite the song playing" },
  { command: "search", name: "Search" },
  { command: "queue", name: "Up next" },
  { command: "help", name: "Keyboard shortcuts" },
];

export const DEFAULT_BINDINGS: Bindings = {
  toggle: ["space", "k"],
  back: ["left"],
  forward: ["right"],
  previous: ["shift+left"],
  next: ["shift+right"],
  volumeDown: ["minus"],
  volumeUp: ["equal"],
  mute: ["m"],
  shuffle: ["s"],
  repeat: ["r"],
  favorite: ["l"],
  search: ["slash"],
  queue: ["q"],
  help: ["shift+slash"],
};

/** The most keys one command takes. */
export const MAX_KEYS = 4;

const KEY = "medleyplay.shortcuts.v2";
const MODIFIERS = ["ctrl", "alt", "shift", "meta"] as const;
const MODIFIER_NAMES: Readonly<Record<string, readonly [label: string, aria: string]>> = {
  ctrl: ["Ctrl", "Control"],
  alt: ["Alt", "Alt"],
  shift: ["Shift", "Shift"],
  meta: ["⌘", "Meta"],
};
/** Keys whose names read better as words or symbols, for people and for assistive technology. */
const KEY_NAMES: Readonly<Record<string, readonly [label: string, aria: string]>> = {
  space: ["Space", "Space"],
  left: ["←", "ArrowLeft"],
  right: ["→", "ArrowRight"],
  up: ["↑", "ArrowUp"],
  down: ["↓", "ArrowDown"],
  enter: ["Enter", "Enter"],
  backspace: ["Backspace", "Backspace"],
};
/** Keys that print a character, by name, with the character a US keyboard prints and its code. */
const PRINTED: Readonly<Record<string, readonly [us: string, code: string]>> = {
  minus: ["-", "Minus"],
  equal: ["=", "Equal"],
  slash: ["/", "Slash"],
  backslash: ["\\", "Backslash"],
  comma: [",", "Comma"],
  period: [".", "Period"],
  semicolon: [";", "Semicolon"],
  quote: ["'", "Quote"],
  backquote: ["`", "Backquote"],
  bracketleft: ["[", "BracketLeft"],
  bracketright: ["]", "BracketRight"],
};
/** Keys that are only ever part of a shortcut, or that the page needs for itself. */
const NOT_ALONE = new Set(["Escape", "Tab"]);

/** What each key prints on this keyboard, by code, once the browser says. */
let layout: ReadonlyMap<string, string> | undefined;

/** Return what the key named `part` prints on this keyboard, or `undefined` if it prints nothing. */
function printedBy(part: string): string | undefined {
  const code = /^[a-z]$/.test(part)
    ? `Key${part.toUpperCase()}`
    : /^\d$/.test(part)
      ? `Digit${part}`
      : PRINTED[part]?.[1];
  const printed = code === undefined ? undefined : layout?.get(code);
  return (printed ?? PRINTED[part]?.[0] ?? (part.length === 1 ? part : undefined))?.toUpperCase();
}

/** Return one binding as people read it, such as `Shift + →`. */
export function labelOf(keys: string): string {
  return keys
    .split("+")
    .map(
      (part) =>
        MODIFIER_NAMES[part]?.[0] ?? KEY_NAMES[part]?.[0] ?? printedBy(part) ?? part.toUpperCase(),
    )
    .join(" + ");
}

/** Return a command's bindings as people read them, such as `Space or K`. */
export function labelsOf(keys: readonly string[]): string {
  return keys.length === 0 ? "None" : keys.map(labelOf).join(" or ");
}

/** Return one binding as `aria-keyshortcuts` writes it, such as `Shift+ArrowRight`. */
export function ariaKeysOf(keys: string): string {
  return keys
    .split("+")
    .map(
      (part) =>
        MODIFIER_NAMES[part]?.[1] ?? KEY_NAMES[part]?.[1] ?? printedBy(part) ?? part.toUpperCase(),
    )
    .join("+");
}

/** Return the hover text and `aria-keyshortcuts` for a control named `name`, on `keys`. */
export function hintOf(
  name: string,
  keys: readonly string[],
): { readonly title: string; readonly "aria-keyshortcuts"?: string } {
  return keys.length === 0
    ? { title: name }
    : {
        title: `${name} (${labelsOf(keys)})`,
        "aria-keyshortcuts": keys.map(ariaKeysOf).join(" "),
      };
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

/**
 * Return `bindings` with `keys` added to `command`'s, the command that already
 * has them, or `full` when `command` has `MAX_KEYS` already.
 */
export function addKeys(
  bindings: Bindings,
  command: Command,
  keys: string,
): { readonly bindings: Bindings } | { readonly taken: Command } | { readonly full: true } {
  const own = bindings[command];
  if (own.includes(keys)) {
    return { bindings };
  }
  const taken = COMMANDS.find(
    (each) => each.command !== command && bindings[each.command].includes(keys),
  );
  if (taken !== undefined) {
    return { taken: taken.command };
  }
  return own.length >= MAX_KEYS
    ? { full: true }
    : { bindings: { ...bindings, [command]: [...own, keys] } };
}

/** Return `bindings` without `keys` among `command`'s. */
export function removeKeys(bindings: Bindings, command: Command, keys: string): Bindings {
  return { ...bindings, [command]: bindings[command].filter((each) => each !== keys) };
}

/** Return the commands `bindings` changes from the defaults, as the server keeps them. */
export function changesOf(bindings: Bindings): SavedShortcuts {
  const changed = COMMANDS.filter(
    ({ command }) => bindings[command].join(",") !== DEFAULT_BINDINGS[command].join(","),
  ).map(({ command }) => [command, bindings[command]] as const);
  return changed.length === 0 ? null : Object.fromEntries(changed);
}

/**
 * Return the bindings `saved` gives: each command it names on its keys, and
 * every other on its defaults.
 *
 * Two commands on the same keys would leave one unreachable, as when a new
 * command's default is keys already saved for another. A saved command that
 * shares keys goes back to its default, until no two share.
 */
export function bindingsOf(saved: unknown): Bindings {
  if (typeof saved !== "object" || saved === null || Array.isArray(saved)) {
    return DEFAULT_BINDINGS;
  }
  const kept = new Map(
    Object.entries(saved).flatMap(([command, keys]): [Command, readonly string[]][] =>
      command in DEFAULT_BINDINGS && Array.isArray(keys)
        ? [
            [
              command as Command,
              [...new Set(keys.filter((each): each is string => typeof each === "string"))]
                .filter((each) => each !== "")
                .slice(0, MAX_KEYS),
            ],
          ]
        : [],
    ),
  );
  for (;;) {
    const bindings: Bindings = { ...DEFAULT_BINDINGS, ...Object.fromEntries(kept) };
    const clashing = [...kept.keys()].filter((command) =>
      COMMANDS.some(
        (other) =>
          other.command !== command &&
          bindings[command].some((keys) => bindings[other.command].includes(keys)),
      ),
    );
    if (clashing.length === 0) {
      return bindings;
    }
    for (const command of clashing) {
      kept.delete(command);
    }
  }
}

/** What this page holds: the bindings, whose they are, and the revision they came from. */
interface Held {
  readonly bindings: Bindings;
  /** The Account signed in; `undefined` before one is. */
  readonly account: number | undefined;
  /** The revision the server last answered; `undefined` until it has. */
  readonly revision: number | undefined;
}

const NOBODY: Held = { bindings: DEFAULT_BINDINGS, account: undefined, revision: undefined };

/** Where this browser keeps its copy of an Account's shortcuts. */
const copyKey = (account: number) => `${KEY}.${String(account)}`;

/** Return the copy of `account`'s shortcuts this browser kept, or the defaults. */
function loadCopy(account: number): Bindings {
  try {
    const copy: unknown = JSON.parse(localStorage.getItem(copyKey(account)) ?? "null");
    return bindingsOf(
      typeof copy === "object" && copy !== null ? Reflect.get(copy, "shortcuts") : null,
    );
  } catch {
    return DEFAULT_BINDINGS;
  }
}

function keepCopy(account: number | undefined, bindings: Bindings): void {
  if (account === undefined) {
    return;
  }
  try {
    localStorage.setItem(copyKey(account), JSON.stringify({ shortcuts: changesOf(bindings) }));
  } catch {
    // A browser that keeps nothing waits for the server's on the next visit.
  }
}

let held = NOBODY;
/** Saves under way; while one is, an older answer from the server doesn't replace what is shown. */
let saving = 0;
const listeners = new Set<() => void>();

function show(next: Held): void {
  held = next;
  for (const listener of listeners) {
    listener();
  }
}

/** Show `account`'s shortcuts: this browser's copy at once, then the server's. */
export async function openAccount(account: number): Promise<void> {
  if (held.account !== account) {
    show({ bindings: loadCopy(account), account, revision: undefined });
  }
  const preferences = await api.preferences();
  const now = held;
  if (
    now.account !== account ||
    saving > 0 ||
    (now.revision !== undefined && preferences.revision < now.revision)
  ) {
    return;
  }
  const bindings = bindingsOf(preferences.shortcuts);
  keepCopy(account, bindings);
  show({ bindings, account, revision: preferences.revision });
}

/**
 * Use `bindings` from now on, here and on every page the Account opens.
 *
 * The page shows them at once; the server keeps them at the revision last read,
 * and if the Account saved them elsewhere since, these, chosen last, replace those.
 */
export async function saveBindings(bindings: Bindings): Promise<void> {
  const { account } = held;
  show({ ...held, bindings });
  keepCopy(account, bindings);
  saving += 1;
  try {
    const shortcuts = changesOf(bindings);
    let saved: Preferences;
    try {
      saved = await api.savePreferences({
        shortcuts,
        revision: held.revision ?? (await api.preferences()).revision,
      });
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 409)) {
        throw error;
      }
      const { revision } = await api.preferences();
      saved = await api.savePreferences({ shortcuts, revision });
    }
    if (held.account === account && held.bindings === bindings) {
      show({ ...held, revision: saved.revision });
    }
  } finally {
    saving -= 1;
  }
}

function subscribe(listener: () => void): () => void {
  // Another tab of this browser that changes them says so here.
  const onStorage = (event: StorageEvent) => {
    const { account } = held;
    if (account !== undefined && event.key === copyKey(account)) {
      show({ ...held, bindings: loadCopy(account) });
    }
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** The bindings in use; every part of the page reads the same ones. */
export function useBindings(): Bindings {
  return useSyncExternalStore(subscribe, () => held.bindings);
}

/** The part of `navigator.keyboard` some browsers have, which says what each key prints. */
interface KeyboardLayouts {
  readonly getLayoutMap: () => Promise<ReadonlyMap<string, string>>;
}

/** Learn what each key prints on this keyboard, where the browser says, and name keys so. */
export function learnLayout(): void {
  const keyboard = (navigator as Navigator & { readonly keyboard?: KeyboardLayouts }).keyboard;
  keyboard?.getLayoutMap().then(
    (map) => {
      layout = new Map(map);
      // The bindings are the same; a new copy draws every label again.
      show({ ...held, bindings: { ...held.bindings } });
    },
    () => {
      // Without the layout, keys are named as a US keyboard prints them.
    },
  );
}

/** Start over as a new page would, with no Account and no layout: for tests. */
export function forgetBindings(): void {
  held = NOBODY;
  layout = undefined;
  saving = 0;
}

/** Name keys as a keyboard printing `map` would: for tests, since jsdom has no layout. */
export function setLayoutForTests(map: ReadonlyMap<string, string> | undefined): void {
  layout = map;
}
