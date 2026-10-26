/**
 * @file The keyboard shortcuts' listeners: each command's keys, wherever focus is on the page.
 *
 * A key the focused control uses itself stays with it: Space presses a button
 * reached with the keyboard, an arrow moves a focused slider, and typing goes
 * into a text box. An open dialog or menu keeps every key.
 */

import { type RefObject, useEffect, useRef } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { COMMANDS, type Command, useBindings } from "../shortcuts";

/** What each command does. */
export type ShortcutHandlers = Readonly<Record<Command, () => void>>;

/** Commands that go on while their keys are held, a step at each repeat. */
const HELD = new Set<Command>(["back", "forward", "volumeDown", "volumeUp"]);

const PRESSES = new Set(["Space", "Enter", "NumpadEnter"]);
const MOVES = new Set([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
  "PageUp",
  "PageDown",
]);
/** Controls a press activates. */
const PRESSED =
  "button, a[href], summary, input:not([type=range]), [role=button], [role=checkbox], [role=switch]";
/** Controls the arrows move along, or move within. */
const MOVED =
  "input[type=range], [role=slider], [role=radio], [role=tab], [role=option], " +
  "[aria-roledescription=sortable]";
/** Inputs that take no typing. */
const UNTYPED = new Set([
  "range",
  "checkbox",
  "radio",
  "button",
  "submit",
  "reset",
  "color",
  "file",
]);

/**
 * Whether `event`'s key belongs to the control it was pressed on, or to an open
 * dialog or menu; `clicked` when that control was focused by the pointer.
 */
function belongsToWidget(event: KeyboardEvent, clicked: boolean): boolean {
  if (document.querySelector("dialog[open]") !== null) {
    return true;
  }
  const target = event.target;
  if (!(target instanceof Element)) {
    return false;
  }
  if (target.closest("[role=menu]") !== null || takesTyping(target)) {
    return true;
  }
  // A clicked button keeps focus, yet Space after a click means play or pause, not click again.
  return (
    (PRESSES.has(event.code) && !clicked && target.closest(PRESSED) !== null) ||
    (MOVES.has(event.code) && target.closest(MOVED) !== null)
  );
}

/** Whether typing goes into `element`; a select picks an option as letters are typed. */
function takesTyping(element: Element): boolean {
  if (element instanceof HTMLInputElement) {
    return !UNTYPED.has(element.type);
  }
  return (
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    (element instanceof HTMLElement && element.isContentEditable)
  );
}

/** Follow whether focus last came by the pointer rather than the keyboard. */
function useFocusByPointer(): RefObject<boolean> {
  const byPointer = useRef(false);
  useEffect(() => {
    let pointing = false;
    const onPointer = () => {
      pointing = true;
    };
    const onKey = () => {
      pointing = false;
    };
    const onFocus = () => {
      byPointer.current = pointing;
    };
    document.addEventListener("pointerdown", onPointer, true);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("focusin", onFocus, true);
    return () => {
      document.removeEventListener("pointerdown", onPointer, true);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("focusin", onFocus, true);
    };
  }, []);
  return byPointer;
}

/** Listen for every command's keys while this is on the page. */
export function Shortcuts({ on }: { readonly on: ShortcutHandlers }) {
  const bindings = useBindings();
  const byPointer = useFocusByPointer();
  const ignored = (event: KeyboardEvent) => belongsToWidget(event, byPointer.current);
  return COMMANDS.map(({ command }) => (
    <Shortcut
      key={command}
      keys={bindings[command]}
      held={HELD.has(command)}
      ignored={ignored}
      onPress={on[command]}
    />
  ));
}

/** One command's listener; a component each, so each calls the hook once. */
function Shortcut({
  keys,
  held,
  ignored,
  onPress,
}: {
  readonly keys: readonly string[];
  readonly held: boolean;
  readonly ignored: (event: KeyboardEvent) => boolean;
  readonly onPress: () => void;
}) {
  useHotkeys(
    keys.join(","),
    (event) => {
      if (held || !event.repeat) {
        onPress();
      }
    },
    {
      // A command with no keys listens for none.
      enabled: keys.length > 0,
      preventDefault: true,
      // The page decides which keys a control keeps, text boxes among them.
      enableOnFormTags: true,
      ignoreEventWhen: ignored,
    },
    [held, onPress],
  );
  return null;
}
