/**
 * @file The views worked out from the Tracks: artists, albums, favorites, downloads, and search.
 *
 * Pure functions over the Track list, so moving between views asks the server
 * nothing. Names are compared folded: without case, width, or the difference
 * between hiragana and katakana.
 */

import type { Track } from "../api";

/** An artist, with how many Tracks are theirs and how long they play. */
export interface Artist {
  /** The name as the first of its Tracks writes it; `""` for Tracks with no artist. */
  readonly name: string;
  readonly count: number;
  readonly durationMs: number;
}

/** An album, under its album artist, or its artist when that is blank. */
export interface Album extends Artist {
  readonly artist: string;
}

/** What a search found. */
export interface Found {
  readonly tracks: readonly Track[];
  readonly artists: readonly Artist[];
  readonly albums: readonly Album[];
}

const KATAKANA = /[ァ-ヶ]/g;
const HIRAGANA_OFFSET = 0x60;

/** Return `text` as search compares it: NFKC, lower case, and katakana as hiragana. */
export function fold(text: string): string {
  return text
    .normalize("NFKC")
    .toLowerCase()
    .replace(KATAKANA, (kana) => String.fromCharCode(kana.charCodeAt(0) - HIRAGANA_OFFSET));
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** Return the Tracks that stand for music in the Library: a file split into songs gives way to them. */
export function songsOf(tracks: readonly Track[]): Track[] {
  return tracks.filter((track) => !track.split);
}

/** Return each artist once, sorted by name as people read them, a blank name first. */
export function artistsOf(tracks: readonly Track[]): Artist[] {
  return groups(tracks, (track) => track.artist).map(({ name, count, durationMs }) => ({
    name,
    count,
    durationMs,
  }));
}

/** Return the Tracks of the artist `name`, compared folded, in the order given. */
export function tracksOfArtist(tracks: readonly Track[], name: string): Track[] {
  const key = fold(name);
  return tracks.filter((track) => fold(track.artist) === key);
}

/** Return each album once, by its artist and then its name. */
export function albumsOf(tracks: readonly Track[]): Album[] {
  return groups(tracks, (track) => `${albumArtistOf(track)}\n${track.album}`)
    .map(({ first, count, durationMs }) => ({
      artist: albumArtistOf(first),
      name: first.album,
      count,
      durationMs,
    }))
    .sort((a, b) => collator.compare(a.artist, b.artist) || collator.compare(a.name, b.name));
}

/** Return the Tracks of the album `name` by `artist`, compared folded, in the order given. */
export function tracksOfAlbum(tracks: readonly Track[], artist: string, name: string): Track[] {
  const artistKey = fold(artist);
  const nameKey = fold(name);
  return tracks.filter(
    (track) => fold(albumArtistOf(track)) === artistKey && fold(track.album) === nameKey,
  );
}

/** Return the favorite Tracks newest added first, the order of the server's Favorites. */
export function favoritesOf(tracks: readonly Track[]): Track[] {
  return tracks
    .filter((track) => track.favorite)
    .sort((a, b) => b.added_at.localeCompare(a.added_at) || b.id - a.id);
}

/** Return the Tracks with a Download kept on the server, in the order given. */
export function downloadedOf(tracks: readonly Track[]): Track[] {
  return tracks.filter((track) => track.downloaded);
}

const haystacks = new WeakMap<Track, string>();

/** Return a Track's title, artist, and album folded, worked out once for each Track. */
function haystackOf(track: Track): string {
  let found = haystacks.get(track);
  if (found === undefined) {
    found = fold(`${track.title}\n${track.artist}\n${track.album}`);
    haystacks.set(track, found);
  }
  return found;
}

/** Return the Tracks, artists, and albums with every word of `query`; a blank query finds none. */
export function search(tracks: readonly Track[], query: string): Found {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return { tracks: [], artists: [], albums: [] };
  }
  const matches = (text: string) => words.every((word) => text.includes(word));
  return {
    tracks: tracks.filter((track) => matches(haystackOf(track))),
    artists: artistsOf(tracks).filter((artist) => matches(fold(artist.name))),
    albums: albumsOf(tracks).filter((album) => matches(fold(album.name))),
  };
}

/** Return the artist a Track's album is listed under: its album artist, or its artist. */
export function albumArtistOf(track: Track): string {
  return track.album_artist === "" ? track.artist : track.album_artist;
}

interface Group {
  readonly name: string;
  readonly first: Track;
  readonly count: number;
  readonly durationMs: number;
}

/** Group `tracks` by `nameOf`, folded, sorted by the name the first Track gives. */
function groups(tracks: readonly Track[], nameOf: (track: Track) => string): Group[] {
  const found = new Map<
    string,
    { name: string; first: Track; count: number; durationMs: number }
  >();
  for (const track of tracks) {
    const name = nameOf(track);
    const key = fold(name);
    const group = found.get(key);
    if (group === undefined) {
      found.set(key, { name, first: track, count: 1, durationMs: track.duration_ms ?? 0 });
    } else {
      group.count += 1;
      group.durationMs += track.duration_ms ?? 0;
    }
  }
  return [...found.values()].sort((a, b) => collator.compare(a.name, b.name));
}
