/**
 * @file Each view of the Library, worked out from the Tracks the page already holds.
 */

import { CaretLeftIcon, HeartIcon, PlaylistIcon } from "@phosphor-icons/react";
import { type ReactNode, useMemo } from "react";

import type { Playlist, Track } from "../api";
import { formatLength } from "../format";
import {
  type Album,
  type Artist,
  albumsOf,
  artistsOf,
  downloadedOf,
  favoritesOf,
  search,
  tracksOfAlbum,
  tracksOfArtist,
} from "../library/views";
import { type Route, hrefOf } from "../routes";
import { SettingsView } from "./SettingsView";
import { type TrackActions, TrackTable } from "./TrackTable";

/** The route id of Favorites, the Playlist of favorites the server keeps for each Account. */
export const FAVORITES = "favorites";

const UNKNOWN_ARTIST = "Unknown artist";
const UNKNOWN_ALBUM = "Unknown album";

/** What every view may show and do. */
export interface ViewProps {
  readonly route: Route;
  readonly tracks: readonly Track[];
  readonly playlists: readonly Playlist[];
  readonly playingId: number | undefined;
  readonly actions: TrackActions;
  /** Whether the Account may change what the household shares, such as the storage limit. */
  readonly admin: boolean;
}

/** The view `route` names. */
export function CurrentView(props: ViewProps) {
  const { route } = props;
  switch (route.view) {
    case "songs":
      return (
        <Songs title="Songs" {...props} empty={<NoMusic />}>
          {props.tracks}
        </Songs>
      );
    case "artists":
      return <Artists tracks={props.tracks} />;
    case "artist":
      return (
        <Songs
          title={route.name || UNKNOWN_ARTIST}
          back={{ view: "artists" }}
          backLabel="Artists"
          {...props}
          empty={<p className="empty">No songs by this artist are in your Library now.</p>}
        >
          {tracksOfArtist(props.tracks, route.name)}
        </Songs>
      );
    case "albums":
      return <Albums tracks={props.tracks} />;
    case "album":
      return (
        <Songs
          title={route.name || UNKNOWN_ALBUM}
          subtitle={route.artist || UNKNOWN_ARTIST}
          back={{ view: "albums" }}
          backLabel="Albums"
          {...props}
          empty={<p className="empty">No songs from this album are in your Library now.</p>}
        >
          {tracksOfAlbum(props.tracks, route.artist, route.name)}
        </Songs>
      );
    case "downloaded":
      return (
        <Songs
          title="Downloaded"
          {...props}
          empty={
            <p className="empty">
              Nothing is downloaded yet. A song you add from a music site is kept here once its
              download finishes.
            </p>
          }
        >
          {downloadedOf(props.tracks)}
        </Songs>
      );
    case "playlists":
      return <Playlists tracks={props.tracks} playlists={props.playlists} />;
    case "playlist":
      return <PlaylistView {...props} id={route.id} />;
    case "search":
      return <SearchResults {...props} query={route.query} />;
    case "settings":
      return <SettingsView admin={props.admin} />;
  }
}

/** A heading, and Tracks in the song table. */
function Songs({
  title,
  subtitle,
  back,
  backLabel,
  children,
  empty,
  playingId,
  actions,
}: Omit<ViewProps, "tracks" | "route" | "playlists" | "admin"> & {
  readonly title: string;
  readonly subtitle?: string | undefined;
  readonly back?: Route;
  readonly backLabel?: string;
  readonly children: readonly Track[];
  readonly empty: ReactNode;
}) {
  return (
    <>
      <ViewHeading title={title} subtitle={subtitle} back={back} backLabel={backLabel}>
        {children.length > 0 && formatLength(children.length, durationOf(children))}
      </ViewHeading>
      <TrackTable tracks={children} playingId={playingId} actions={actions} empty={empty} />
    </>
  );
}

function ViewHeading({
  title,
  subtitle,
  back,
  backLabel,
  children,
}: {
  readonly title: string;
  readonly subtitle?: string | undefined;
  readonly back?: Route | undefined;
  readonly backLabel?: string | undefined;
  readonly children?: ReactNode;
}) {
  return (
    <header className="view-heading">
      {back !== undefined && (
        <a className="back" href={hrefOf(back)}>
          <CaretLeftIcon weight="bold" aria-hidden />
          {backLabel}
        </a>
      )}
      <h2 className="section">{title}</h2>
      {subtitle !== undefined && <p className="subtitle">{subtitle}</p>}
      {children !== undefined && children !== false && <p className="meta">{children}</p>}
    </header>
  );
}

function Artists({ tracks }: { readonly tracks: readonly Track[] }) {
  const artists = useMemo(() => artistsOf(tracks), [tracks]);
  return (
    <>
      <ViewHeading title="Artists">
        {artists.length > 0 && `${String(artists.length)} artists`}
      </ViewHeading>
      {artists.length === 0 ? <NoMusic /> : <ArtistList artists={artists} />}
    </>
  );
}

function ArtistList({ artists }: { readonly artists: readonly Artist[] }) {
  return (
    <ul className="groups" aria-label="Artists">
      {artists.map((artist) => (
        <li key={artist.name}>
          <a href={hrefOf({ view: "artist", name: artist.name })}>
            <span className="avatar" aria-hidden>
              {initialOf(artist.name)}
            </span>
            <span className="group-name">{artist.name || UNKNOWN_ARTIST}</span>
            <span className="group-meta">{formatLength(artist.count, artist.durationMs)}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function Albums({ tracks }: { readonly tracks: readonly Track[] }) {
  const albums = useMemo(() => albumsOf(tracks), [tracks]);
  return (
    <>
      <ViewHeading title="Albums">
        {albums.length > 0 && `${String(albums.length)} albums`}
      </ViewHeading>
      {albums.length === 0 ? <NoMusic /> : <AlbumList albums={albums} />}
    </>
  );
}

function AlbumList({ albums }: { readonly albums: readonly Album[] }) {
  return (
    <ul className="groups" aria-label="Albums">
      {albums.map((album) => (
        <li key={`${album.artist}\n${album.name}`}>
          <a href={hrefOf({ view: "album", artist: album.artist, name: album.name })}>
            <span className="cover-tile" aria-hidden>
              {initialOf(album.name)}
            </span>
            <span className="group-name">{album.name || UNKNOWN_ALBUM}</span>
            <span className="group-meta">
              {album.artist || UNKNOWN_ARTIST}, {formatLength(album.count, album.durationMs)}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function Playlists({
  tracks,
  playlists,
}: {
  readonly tracks: readonly Track[];
  readonly playlists: readonly Playlist[];
}) {
  // Favorites is worked out from the hearts here, so a heart counts at once.
  const favorites = favoritesOf(tracks);
  return (
    <>
      <ViewHeading title="Playlists" />
      <ul className="groups" aria-label="Playlists">
        {playlists.some((playlist) => playlist.builtin === FAVORITES) && (
          <li>
            <a href={hrefOf({ view: "playlist", id: FAVORITES })}>
              <span className="cover-tile favorites" aria-hidden>
                <HeartIcon weight="fill" />
              </span>
              <span className="group-name">Favorites</span>
              <span className="group-meta">
                {formatLength(favorites.length, durationOf(favorites))}
              </span>
            </a>
          </li>
        )}
        {ownPlaylists(playlists).map((playlist) => {
          const held = tracksOfPlaylist(tracks, playlist);
          return (
            <li key={playlist.id}>
              <a href={hrefOf({ view: "playlist", id: playlist.id })}>
                <span className="cover-tile" aria-hidden>
                  <PlaylistIcon weight="duotone" />
                </span>
                <span className="group-name">{playlist.name}</span>
                <span className="group-meta">
                  {playlist.rules === null ? "" : "Smart, "}
                  {formatLength(held.length, durationOf(held))}
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function PlaylistView({ id, ...props }: ViewProps & { readonly id: string }) {
  const playlist = props.playlists.find((each) => each.id === id);
  if (id === FAVORITES || playlist?.builtin === FAVORITES) {
    return (
      <Songs
        title="Favorites"
        back={{ view: "playlists" }}
        backLabel="Playlists"
        {...props}
        empty={<p className="empty">No favorites yet. Tap a song's heart to keep it here.</p>}
      >
        {favoritesOf(props.tracks)}
      </Songs>
    );
  }
  if (playlist === undefined) {
    return (
      <>
        <ViewHeading title="Playlist" back={{ view: "playlists" }} backLabel="Playlists" />
        <p className="empty">This Playlist isn't here any more.</p>
      </>
    );
  }
  return (
    <Songs
      title={playlist.name}
      subtitle={playlist.unreadable === "" ? undefined : playlist.unreadable}
      back={{ view: "playlists" }}
      backLabel="Playlists"
      {...props}
      empty={<p className="empty">This Playlist has no songs yet.</p>}
    >
      {tracksOfPlaylist(props.tracks, playlist)}
    </Songs>
  );
}

function SearchResults({ query, ...props }: ViewProps & { readonly query: string }) {
  const found = useMemo(() => search(props.tracks, query), [props.tracks, query]);
  if (query.trim() === "") {
    return (
      <>
        <ViewHeading title="Search" />
        <p className="empty">Type a song, an artist, or an album to find it in your Library.</p>
      </>
    );
  }
  const nothing =
    found.tracks.length === 0 && found.artists.length === 0 && found.albums.length === 0;
  return (
    <>
      <ViewHeading title={`Results for “${query}”`} />
      {nothing && <p className="empty">Nothing in your Library matches “{query}”.</p>}
      {found.artists.length > 0 && (
        <section aria-label="Artists found">
          <h3 className="found">Artists</h3>
          <ArtistList artists={found.artists} />
        </section>
      )}
      {found.albums.length > 0 && (
        <section aria-label="Albums found">
          <h3 className="found">Albums</h3>
          <AlbumList albums={found.albums} />
        </section>
      )}
      {found.tracks.length > 0 && (
        <section aria-label="Songs found">
          <h3 className="found">Songs</h3>
          <TrackTable
            tracks={found.tracks}
            playingId={props.playingId}
            actions={props.actions}
            empty={null}
          />
        </section>
      )}
    </>
  );
}

function NoMusic() {
  return (
    <p className="empty">
      No music yet. An admin adds a Library of your own music in <a href="/docs">the API</a>, and
      its songs appear here.
    </p>
  );
}

/** Return the Account's own Playlists, leaving out the ones the server keeps. */
function ownPlaylists(playlists: readonly Playlist[]): Playlist[] {
  return playlists.filter((playlist) => playlist.builtin === null);
}

/** Return a Playlist's Tracks the page holds, in its order, a Track as often as it appears. */
function tracksOfPlaylist(tracks: readonly Track[], playlist: Playlist): Track[] {
  const byId = new Map(tracks.map((track) => [track.id, track]));
  return playlist.track_ids.flatMap((id) => {
    const track = byId.get(id);
    return track === undefined ? [] : [track];
  });
}

function durationOf(tracks: readonly Track[]): number {
  return tracks.reduce((total, track) => total + (track.duration_ms ?? 0), 0);
}

const letters = new Intl.Segmenter();

/** Return the first letter of `name` as a person sees it, such as `初` or `É`. */
function initialOf(name: string): string {
  const [first] = letters.segment(name.trim());
  return first?.segment.toUpperCase() ?? "?";
}
