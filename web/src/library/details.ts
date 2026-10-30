/**
 * @file A Track's details as the edit dialog shows them: the household's own values, and what shows.
 *
 * The dialog keeps the household's values as typed. Every other box shows what the
 * server would show with them, worked out by `shownOf`, the server's rule: a field
 * shows the first origin's value, and the album fields come together from the first
 * origin naming an album. So naming an album of the household's own empties the
 * file's track number at once, as saving would.
 */

import type { Detail, Details, Found, Origin } from "../api";

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

/** Detail values, keyed by detail. */
export type Values = Partial<Readonly<Record<Detail, string | number>>>;

/** What each origin says. */
export type Origins = Details["origins"];

/** What each field shows, and where it came from. */
export type Shown = Partial<Readonly<Record<Detail, Found>>>;

/** The household's values as their boxes hold them; a field absent is not the household's. */
export type Own = Partial<Readonly<Record<Detail, string>>>;

/** The origins in the order the shown value is chosen. */
const ORIGINS: readonly Origin[] = [
  "household",
  "files",
  "musicbrainz",
  "video",
  "album_file",
  "file_name",
];

/** The fields that describe the release a Track is on, shown from one origin. */
const ALBUM_FIELDS: readonly Detail[] = [
  "album",
  "album_artist",
  "track_number",
  "disc_number",
  "year",
];

const KINDS = new Map(DETAIL_FIELDS.map((field) => [field.name, field.kind]));

/** Return what each field shows from `origins`, as the server chooses it. */
export function shownOf(origins: Origins): Shown {
  const shown: Partial<Record<Detail, Found>> = {};
  const first = (field: Detail, from: readonly Origin[]) => {
    for (const origin of from) {
      const value = origins[origin]?.[field];
      if (value !== undefined) {
        shown[field] = { value, origin };
        return;
      }
    }
  };
  for (const { name } of DETAIL_FIELDS) {
    if (!ALBUM_FIELDS.includes(name)) {
      first(name, ORIGINS);
    }
  }
  // Without a named album, each album field falls back on its own.
  const named = ORIGINS.find((origin) => Boolean(origins[origin]?.album));
  for (const field of ALBUM_FIELDS) {
    first(field, named === undefined ? ORIGINS : ["household", named]);
  }
  return shown;
}

/** Return the household's values as their boxes hold them. */
export function ownOf(details: Details): Own {
  return Object.fromEntries(
    Object.entries(details.origins.household ?? {}).map(([field, value]) => [field, String(value)]),
  );
}

/**
 * Return the household's values from the boxes: text trimmed, numbers as numbers.
 * An empty number box is no value, so what is found shows.
 */
export function valuesOf(own: Own): Values {
  const values: Partial<Record<Detail, string | number>> = {};
  for (const [field, typed] of Object.entries(own) as [Detail, string][]) {
    const trimmed = typed.trim();
    if (KINDS.get(field) === "number") {
      if (trimmed !== "") {
        values[field] = Number(trimmed);
      }
    } else {
      values[field] = trimmed;
    }
  }
  return values;
}

/** Return what every origin but the household says. */
export function foundOf(details: Details): Origins {
  return without(details.origins, "household");
}

/**
 * Return `own` without each value the household changed to what would show anyway,
 * read as saving reads it: so " Melt" over the file's "Melt", "03" over its 3, or an
 * emptied box where nothing is found. Saving those would only pin the found value. A
 * value the household already had stays.
 */
export function settle(details: Details, own: Own): Own {
  const had = valuesOf(ownOf(details));
  let settled = own;
  for (const { name, kind } of DETAIL_FIELDS) {
    const typed = settled[name];
    const value = typed === undefined ? undefined : valuesOf({ [name]: typed })[name];
    if (typed === undefined || value === had[name]) {
      continue;
    }
    const others = without(settled, name);
    const shows = shownWith(details, others)[name]?.value;
    if (kind === "text" ? (value ?? "") === (shows ?? "") : value === shows) {
      settled = others;
    }
  }
  return settled;
}

/** Return what each field would show with the household's values `own`. */
export function previewOf(details: Details, own: Own): Shown {
  return shownWith(details, settle(details, own));
}

/** Return the text of `name`'s box: the household's own, or what would show. */
export function boxText(details: Details, own: Own, name: Detail): string {
  return own[name] ?? String(previewOf(details, own)[name]?.value ?? "");
}

/**
 * Return what saving changes: each household value set, or `null` for one dropped,
 * so the next origin shows. A value the household already had is left out.
 */
export function changesOf(
  details: Details,
  own: Own,
): Partial<Record<Detail, string | number | null>> {
  const before = valuesOf(ownOf(details));
  const after = valuesOf(settle(details, own));
  const changes: Partial<Record<Detail, string | number | null>> = {};
  for (const { name } of DETAIL_FIELDS) {
    if (before[name] !== after[name]) {
      changes[name] = after[name] ?? null;
    }
  }
  return changes;
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
  for (const origin of ORIGINS) {
    const value = details.origins[origin]?.[name];
    if (origin === "household" || value === undefined || seen.has(String(value))) {
      continue;
    }
    seen.add(String(value));
    found.push({ value: String(value), origin });
  }
  return found;
}

function shownWith(details: Details, own: Own): Shown {
  return shownOf({ ...foundOf(details), household: valuesOf(own) });
}

function without<T extends object, K extends keyof T & string>(record: T, key: K): Omit<T, K> {
  return Object.fromEntries(Object.entries(record).filter(([name]) => name !== key)) as Omit<T, K>;
}
