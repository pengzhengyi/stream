/**
 * @file A song's menu: its less frequent actions, behind a "…" button.
 *
 * The one module that knows Radix's dropdown menu, which handles the keyboard,
 * the focus, and keeping the menu on screen; the rest of the client hands it a
 * Track and callbacks. The menu draws in a portal, so a table row doesn't clip it.
 */

import {
  DotsThreeIcon,
  ListPlusIcon,
  MicrophoneStageIcon,
  PencilSimpleIcon,
  PlaylistIcon,
  QueueIcon,
  VinylRecordIcon,
} from "@phosphor-icons/react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import type { ReactNode } from "react";

import type { Track } from "../api";
import { albumArtistOf } from "../library/views";
import { navigate } from "../routes";

/** What a song's menu does besides going to its artist or album. */
export interface TrackMenuActions {
  readonly onPlayNext: (track: Track) => void;
  readonly onAdd: (track: Track) => void;
  readonly onAddToPlaylist: (track: Track) => void;
  readonly onEditDetails: (track: Track) => void;
}

/** The "…" button of `track`, and its menu; `queueing` offers Play next and Add to queue. */
export function TrackMenu({
  track,
  actions,
  queueing,
}: {
  readonly track: Track;
  readonly actions: TrackMenuActions;
  readonly queueing: boolean;
}) {
  const playable = track.availability === "ok";
  return (
    <Menu.Root modal={false}>
      <Menu.Trigger asChild>
        <button
          type="button"
          className="icon more"
          aria-label={`More actions for ${track.title}`}
          title="More actions"
        >
          <DotsThreeIcon weight="bold" aria-hidden />
        </button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className="track-menu" align="end" sideOffset={4} collisionPadding={8}>
          {queueing && (
            <>
              <Item
                icon={<QueueIcon />}
                disabled={!playable}
                onSelect={() => {
                  actions.onPlayNext(track);
                }}
              >
                Play next
              </Item>
              <Item
                icon={<ListPlusIcon />}
                disabled={!playable}
                onSelect={() => {
                  actions.onAdd(track);
                }}
              >
                Add to queue
              </Item>
              <Menu.Separator className="track-menu-line" />
            </>
          )}
          <Item
            icon={<MicrophoneStageIcon />}
            onSelect={() => {
              navigate({ view: "artist", name: track.artist });
            }}
          >
            Go to artist
          </Item>
          <Item
            icon={<VinylRecordIcon />}
            onSelect={() => {
              navigate({ view: "album", artist: albumArtistOf(track), name: track.album });
            }}
          >
            Go to album
          </Item>
          <Menu.Separator className="track-menu-line" />
          <Item
            icon={<PlaylistIcon />}
            onSelect={() => {
              actions.onAddToPlaylist(track);
            }}
          >
            Add to playlist…
          </Item>
          <Item
            icon={<PencilSimpleIcon />}
            onSelect={() => {
              actions.onEditDetails(track);
            }}
          >
            Edit details…
          </Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

function Item({
  icon,
  children,
  disabled = false,
  onSelect,
}: {
  readonly icon: ReactNode;
  readonly children: string;
  readonly disabled?: boolean;
  readonly onSelect: () => void;
}) {
  return (
    <Menu.Item className="track-menu-item" disabled={disabled} onSelect={onSelect}>
      <span className="track-menu-icon" aria-hidden>
        {icon}
      </span>
      {children}
    </Menu.Item>
  );
}
