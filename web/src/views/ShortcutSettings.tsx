/**
 * @file Changing the keyboard shortcuts: each command's keys, added from the next press or removed.
 *
 * Choosing Add keys waits for keys on that button: the next press, with any
 * modifiers held, joins the command's keys, unless another command has them.
 * Escape, or moving away, adds nothing. The keys are the Account's, so they
 * follow it to any browser.
 */

import { XIcon } from "@phosphor-icons/react";
import { type KeyboardEvent, useRef, useState } from "react";

import {
  type Bindings,
  COMMANDS,
  type Command,
  DEFAULT_BINDINGS,
  MAX_KEYS,
  addKeys,
  belongsToBrowser,
  bindingOf,
  changesOf,
  labelOf,
  removeKeys,
  saveBindings,
  useBindings,
} from "../shortcuts";

/** What was last said about a change; `refused` when it didn't happen, or wasn't kept. */
interface Note {
  readonly text: string;
  readonly refused: boolean;
}

const QUIET: Note = { text: "", refused: false };

const nameOf = (command: Command) => COMMANDS.find((each) => each.command === command)?.name;

/** What the Settings section for the keyboard shortcuts holds. */
export function ShortcutSettings() {
  const bindings = useBindings();
  const [recording, setRecording] = useState<Command | undefined>(undefined);
  const [note, setNote] = useState<Note>(QUIET);
  // Some browsers click a button as Space comes up, so the release of a press taken is kept too.
  const taken = useRef<string | undefined>(undefined);
  const defaults = changesOf(bindings) === null;

  /** Use `next` from now on, saying `said`, or why the server didn't keep it. */
  const save = (next: Bindings, said: string) => {
    setNote({ text: said, refused: false });
    saveBindings(next).catch((failure: unknown) => {
      const reason = failure instanceof Error ? failure.message : String(failure);
      setNote({
        text: `The server didn't keep them: ${reason}. This browser has them until it does.`,
        refused: true,
      });
    });
  };

  const record = (command: Command, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setRecording(undefined);
      setNote(QUIET);
      return;
    }
    const keys = bindingOf(event.nativeEvent);
    if (keys === undefined) {
      // A modifier on its own waits for its key; Tab moves on, as it always does.
      return;
    }
    // The press is the new keys, not a press of the button or a shortcut.
    event.preventDefault();
    event.stopPropagation();
    taken.current = event.code;
    if (belongsToBrowser(keys)) {
      setNote({ text: `The browser keeps ${labelOf(keys)}. Press other keys.`, refused: true });
      return;
    }
    const added = addKeys(bindings, command, keys);
    if ("taken" in added) {
      setNote({
        text: `${labelOf(keys)} is already ${nameOf(added.taken) ?? ""}. Press other keys.`,
        refused: true,
      });
      return;
    }
    setRecording(undefined);
    if ("full" in added) {
      setNote({
        text: `${nameOf(command) ?? ""} has ${String(MAX_KEYS)} keys; remove one first.`,
        refused: true,
      });
      return;
    }
    save(added.bindings, `${nameOf(command) ?? ""} now also has ${labelOf(keys)}.`);
  };

  return (
    <>
      <p className="hint">Keys for the player, kept with your account.</p>
      <ul className="shortcut-settings">
        {COMMANDS.map(({ command, name }) => {
          const waiting = recording === command;
          return (
            <li key={command} className="shortcut-row">
              <span className="shortcut-name">{name}</span>
              <span className="shortcut-keys">
                {bindings[command].length === 0 && <span className="no-keys">None</span>}
                {bindings[command].map((keys) => (
                  <span key={keys} className="key-chip">
                    <kbd>{labelOf(keys)}</kbd>
                    <button
                      type="button"
                      className="icon remove-keys"
                      aria-label={`Remove ${labelOf(keys)} from ${name}`}
                      title={`Remove ${labelOf(keys)}`}
                      onClick={() => {
                        save(
                          removeKeys(bindings, command, keys),
                          `${name} no longer has ${labelOf(keys)}.`,
                        );
                      }}
                    >
                      <XIcon weight="bold" aria-hidden />
                    </button>
                  </span>
                ))}
              </span>
              <button
                type="button"
                className={waiting ? "outline change-keys waiting" : "outline change-keys"}
                aria-label={waiting ? `Press keys to add to ${name}` : `Add keys to ${name}`}
                onClick={() => {
                  setRecording(command);
                  setNote(QUIET);
                }}
                onKeyDown={(event) => {
                  if (waiting) {
                    record(command, event);
                  }
                }}
                onKeyUp={(event) => {
                  if (event.code === taken.current) {
                    taken.current = undefined;
                    event.preventDefault();
                  }
                }}
                onBlur={() => {
                  if (waiting) {
                    setRecording(undefined);
                  }
                }}
              >
                {waiting ? "Press keys…" : "Add keys"}
              </button>
            </li>
          );
        })}
      </ul>
      <p className={note.refused ? "hint refused" : "hint saved"} role="status">
        {note.text}
      </p>
      <button
        type="button"
        className="secondary outline"
        disabled={defaults}
        onClick={() => {
          setRecording(undefined);
          save(DEFAULT_BINDINGS, "Back to the usual keys.");
        }}
      >
        Reset to defaults
      </button>
    </>
  );
}
