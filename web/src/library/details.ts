/**
 * @file A Track's details as the edit dialog shows them, and which edits are the household's.
 *
 * An edit is the household's only when it differs from what would show without it,
 * so typing a found value back drops the household's value rather than pinning it.
 */

import type { Detail, Details, Origin } from "../api";

/** A detail as the dialog lays it out. */
export interface DetailField {
  readonly name: Detail;
  readonly label: string;
  readonly kind: "text" | "number";
  readonly group: "song" | "album";
}

/** Every detail, in the dialog's order. */
export const DETAIL_FIELDS: readonly DetailField[] = [
  { name: "title", label: "Title", kind: "text", group: "song" },
  { name: "artist", label: "Artist", kind: "text", group: "song" },
  { name: "genre", label: "Genre", kind: "text", group: "song" },
  { name: "album", label: "Album", kind: "text", group: "album" },
  { name: "album_artist", label: "Album artist", kind: "text", group: "album" },
  { name: "track_number", label: "Track", kind: "number", group: "album" },
  { name: "disc_number", label: "Disc", kind: "number", group: "album" },
  { name: "year", label: "Year", kind: "number", group: "album" },
];

/** Where a value came from, as the dialog says it. */
export const ORIGIN_LABELS: Readonly<Record<Origin, string>> = {
  household: "yours",
  files: "the file's tags",
  musicbrainz: "MusicBrainz",
  video: "the video",
  album_file: "the album file",
  file_name: "the file's name",
};

/** What each field's box holds: text as typed, keyed by detail. */
export type Inputs = Readonly<Record<Detail, string>>;

/** Return the boxes filled with what each field shows now; a field nothing gives is empty. */
export function inputsOf(details: Details): Inputs {
  return Object.fromEntries(
    DETAIL_FIELDS.map(({ name }) => [name, String(details.shown[name]?.value ?? "")]),
  ) as Inputs;
}

/** Return what `name` would show without the household's value, as box text. */
export function foundText(details: Details, name: Detail): string {
  return String(details.found[name]?.value ?? "");
}

/**
 * Return the household's values from the boxes: each field whose box differs from
 * what was found. A text box emptied shows nothing; an empty number box is no value.
 */
export function householdOf(
  details: Details,
  inputs: Inputs,
): Partial<Record<Detail, string | number>> {
  const values: Partial<Record<Detail, string | number>> = {};
  for (const { name, kind } of DETAIL_FIELDS) {
    const typed = inputs[name].trim();
    if (typed === foundText(details, name) || (kind === "number" && typed === "")) {
      continue;
    }
    values[name] = kind === "number" ? Number(typed) : typed;
  }
  return values;
}

/** A value an origin gives for a field, other than the one in its box. */
export interface Alternative {
  readonly value: string;
  readonly origin: Origin;
}

/** Return the values other origins give for `name`, each once, unlike `typed`. */
export function alternativesOf(details: Details, name: Detail, typed: string): Alternative[] {
  const seen = new Set([typed.trim()]);
  const found: Alternative[] = [];
  for (const [origin, values] of Object.entries(details.origins) as [
    Origin,
    Partial<Record<Detail, string | number>>,
  ][]) {
    const value = values[name];
    if (origin === "household" || value === undefined || seen.has(String(value))) {
      continue;
    }
    seen.add(String(value));
    found.push({ value: String(value), origin });
  }
  return found;
}
