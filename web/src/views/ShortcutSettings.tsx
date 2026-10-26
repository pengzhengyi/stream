/**
 * @file Changing the keyboard shortcuts: each command's keys, recorded from the next press.
 *
 * Choosing Change waits for keys on that button: the next press, with any
 * modifiers held, becomes the command's keys, unless another command has them.
 * Escape, or moving away, keeps the keys it had.
 */

import { type KeyboardEvent, useState } from "react";

import {
  COMMANDS,
  type Command,
  DEFAULT_BINDINGS,
  bindingOf,
  labelOf,
  rebind,
  saveBindings,
  useBindings,
} from "../shortcuts";

/** What was last said about a change; `refused` when the keys were another command's. */
interface Note {
  readonly text: string;
  readonly refused: boolean;
}

const QUIET: Note = { text: "", refused: false };

const nameOf = (command: Command) => COMMANDS.find((each) => each.command === command)?.name;

/** The Settings section for the keyboard shortcuts. */
export function ShortcutSettings() {
  const bindings = useBindings();
  const [recording, setRecording] = useState<Command | undefined>(undefined);
  const [note, setNote] = useState<Note>(QUIET);
  const defaults = COMMANDS.every(({ command }) => bindings[command] === DEFAULT_BINDINGS[command]);

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
    const changed = rebind(bindings, command, keys);
    if ("taken" in changed) {
      setNote({
        text: `${labelOf(keys)} is already ${nameOf(changed.taken) ?? ""}. Press other keys.`,
        refused: true,
      });
      return;
    }
    saveBindings(changed.bindings);
    setRecording(undefined);
    setNote({ text: `${nameOf(command) ?? ""} is now ${labelOf(keys)}.`, refused: false });
  };

  return (
    <section className="settings-section" aria-labelledby="keyboard-shortcuts">
      <h3 id="keyboard-shortcuts">Keyboard shortcuts</h3>
      <p className="hint">Keys for the player, kept in this browser.</p>
      <ul className="shortcut-settings">
        {COMMANDS.map(({ command, name }) => {
          const waiting = recording === command;
          return (
            <li key={command} className="shortcut-row">
              <span className="shortcut-name">{name}</span>
              <kbd>{labelOf(bindings[command])}</kbd>
              <button
                type="button"
                className={waiting ? "outline change-keys waiting" : "outline change-keys"}
                aria-label={waiting ? `Press new keys for ${name}` : `Change keys for ${name}`}
                onClick={() => {
                  setRecording(command);
                  setNote(QUIET);
                }}
                onKeyDown={(event) => {
                  if (waiting) {
                    record(command, event);
                  }
                }}
                onBlur={() => {
                  if (waiting) {
                    setRecording(undefined);
                  }
                }}
              >
                {waiting ? "Press keys…" : "Change"}
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
          saveBindings(DEFAULT_BINDINGS);
          setRecording(undefined);
          setNote({ text: "Back to the usual keys.", refused: false });
        }}
      >
        Reset to defaults
      </button>
    </section>
  );
}
