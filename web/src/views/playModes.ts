/**
 * @file What the play modes are called, and what is said on changing them.
 */

import type { Repeat } from "../player/queue";

/** Each repeat mode: its label, and what is said on choosing it. */
export const REPEATS: Readonly<Record<Repeat, { readonly label: string; readonly said: string }>> =
  {
    off: { label: "Repeat: off", said: "Repeat off." },
    all: { label: "Repeat: all", said: "Repeating the queue." },
    one: { label: "Repeat: one", said: "Repeating this Track." },
  };

/** What is said on turning shuffle on or off. */
export const shuffleSaid = (on: boolean) => (on ? "Shuffle on." : "Shuffle off.");
