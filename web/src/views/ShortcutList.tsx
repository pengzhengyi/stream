/**
 * @file The list of keyboard shortcuts: each command and its keys, and where to change them.
 */

import { useRef } from "react";

import { hrefOf } from "../routes";
import { COMMANDS, labelOf, useBindings } from "../shortcuts";
import { Modal } from "./Modal";

/** Every command and its keys, in a modal. */
export function ShortcutList({ onClose }: { readonly onClose: () => void }) {
  const bindings = useBindings();
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  return (
    <Modal
      ref={dialog}
      className="shortcut-list"
      labelledBy="shortcut-list-title"
      onClose={onClose}
    >
      <div className="card">
        <h2 id="shortcut-list-title">Keyboard shortcuts</h2>
        <dl className="shortcuts">
          {COMMANDS.map(({ command, name }) => (
            <div key={command} className="shortcut">
              <dt>{name}</dt>
              <dd>
                <kbd>{labelOf(bindings[command])}</kbd>
              </dd>
            </div>
          ))}
        </dl>
        <footer className="dialog-buttons">
          <a className="change-keys" href={hrefOf({ view: "settings" })} onClick={close}>
            Change them in Settings
          </a>
          <button type="button" className="dialog-button" onClick={close}>
            Close
          </button>
        </footer>
      </div>
    </Modal>
  );
}
