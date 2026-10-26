/**
 * @file A modal: a card over a dimmed page, open while it is on the page.
 *
 * A native modal `<dialog>`, so focus stays in it and the page behind is inert.
 * Escape or a click outside the card closes it; so does `ref.current.close()`.
 */

import { type ReactNode, type RefObject, useEffect } from "react";

/** A modal named by the element `labelledBy`; the caller keeps `ref` to close it. */
export function Modal({
  ref,
  className,
  labelledBy,
  onClose,
  children,
}: {
  readonly ref: RefObject<HTMLDialogElement | null>;
  readonly className: string;
  readonly labelledBy: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
}) {
  useEffect(() => {
    const element = ref.current;
    element?.showModal();
    return () => {
      element?.close();
    };
  }, [ref]);
  return (
    <dialog
      ref={ref}
      className={`modal ${className}`}
      aria-labelledby={labelledBy}
      onClose={onClose}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.currentTarget.close();
        }
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog itself, outside its card.
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      {children}
    </dialog>
  );
}
