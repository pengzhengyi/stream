/**
 * @file A range input that shows where it is held, and commits once let go.
 */

import { type ChangeEvent, type RefObject, useEffect, useEffectEvent, useState } from "react";

/** Where a range input is held while dragged, and the `onChange` that follows it. */
export interface HeldRange {
  /** Where the thumb is held, until it is let go. */
  readonly held: number | undefined;
  readonly onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Follow the range input `input` while it is dragged, and call `onLetGo` once with
 * where it ends. A key press moves it and lets go at once.
 */
export function useHeldRange(
  input: RefObject<HTMLInputElement | null>,
  onLetGo: (value: number) => void,
): HeldRange {
  const [held, setHeld] = useState<number | undefined>(undefined);
  const letGo = useEffectEvent((element: HTMLInputElement) => {
    onLetGo(Number(element.value));
    setHeld(undefined);
  });
  useEffect(() => {
    const element = input.current;
    if (element === null) {
      return;
    }
    // `change` fires when the drag ends, or at once for a key; `input` fires all along.
    const onChange = () => {
      letGo(element);
    };
    element.addEventListener("change", onChange);
    return () => {
      element.removeEventListener("change", onChange);
    };
  }, [input]);
  return {
    held,
    onChange: (event) => {
      setHeld(Number(event.currentTarget.value));
    },
  };
}
