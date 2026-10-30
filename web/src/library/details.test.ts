import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { type Origins, type Shown, shownOf } from "./details";

/** The cases the server's own rule is checked against too, in `tests/support`. */
interface Shared {
  readonly cases: readonly { name: string; origins: Origins; shown: Shown }[];
}

const SHARED = JSON.parse(
  readFileSync(join(__dirname, "../../../tests/support/shown_details.json"), "utf8"),
) as Shared;

describe("what a Track shows", () => {
  it.each(SHARED.cases.map((each) => [each.name, each] as const))(
    "%s, as the server shows it",
    (_, { origins, shown }) => {
      expect(shownOf(origins)).toEqual(shown);
    },
  );
});
