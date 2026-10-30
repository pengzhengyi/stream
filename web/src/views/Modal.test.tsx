import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "./Modal";

function Open({
  locked = false,
  onClose,
}: {
  readonly locked?: boolean;
  readonly onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  return (
    <Modal ref={ref} className="test" labelledBy="test-title" locked={locked} onClose={onClose}>
      <div className="card">
        <h2 id="test-title">Pick one</h2>
        <input aria-label="Name" />
      </div>
    </Modal>
  );
}

function renderModal(locked = false) {
  const onClose = vi.fn();
  render(<Open locked={locked} onClose={onClose} />);
  return { dialog: screen.getByRole("dialog", { name: "Pick one" }), onClose };
}

/**
 * Ask `dialog` to close as a browser does for a close request that isn't the Escape
 * key, such as Android's Back button: a `cancel` event, then closing unless it was cancelled.
 */
function requestClose(dialog: HTMLElement) {
  if (fireEvent(dialog, new Event("cancel", { cancelable: true }))) {
    (dialog as HTMLDialogElement).close();
  }
}

describe("a modal", () => {
  it("closes on a close request such as the Back button", () => {
    const { dialog, onClose } = renderModal();

    requestClose(dialog);

    expect(dialog).not.toHaveAttribute("open");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("stays open on a close request while locked", () => {
    const { dialog, onClose } = renderModal(true);

    requestClose(dialog);

    expect(dialog).toHaveAttribute("open");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on a click outside its card", async () => {
    const { dialog, onClose } = renderModal();

    await userEvent.click(dialog);

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("stays open when a press in its card is released outside it", async () => {
    const { dialog, onClose } = renderModal();

    await userEvent.pointer([
      { keys: "[MouseLeft>]", target: screen.getByRole("textbox", { name: "Name" }) },
      { target: dialog },
      { keys: "[/MouseLeft]", target: dialog },
    ]);

    expect(dialog).toHaveAttribute("open");
    expect(onClose).not.toHaveBeenCalled();
  });
});
