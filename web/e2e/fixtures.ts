/**
 * @file What the end-to-end tests share: Alice, where the music is, and her saved session.
 */

import path from "node:path";

/** Where `serve.py` writes the music and the data folder. */
export const MUSIC = path.resolve(import.meta.dirname, "../.cache/e2e");

/** Alice's session, saved by the setup project. */
export const SIGNED_IN = path.join(MUSIC, "alice.json");

/** Alice, the admin. */
export const ALICE = {
  username: "alice",
  display_name: "Alice",
  password: "correct horse battery",
};
