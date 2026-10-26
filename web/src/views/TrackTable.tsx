/**
 * @file The song table: Tracks to sort, rate, and play, drawing only the rows on screen.
 *
 * The one module that knows TanStack Table and TanStack Virtual; the rest of the
 * client hands it Tracks and callbacks. Rows above and below the screen are
 * spacer rows hidden from screen readers, while `aria-rowcount` and
 * `aria-rowindex` count every Track.
 */

import {
  CaretDownIcon,
  CaretUpIcon,
  HeartIcon,
  ListPlusIcon,
  QueueIcon,
  SlidersHorizontalIcon,
  StarIcon,
} from "@phosphor-icons/react";
import {
  type ColumnDef,
  type ColumnSizingState,
  type Row,
  type ColumnVisibilityState,
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  createSortedRowModel,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { type ReactNode, useEffect, useRef, useState } from "react";

import type { Track } from "../api";
import { formatTime } from "../format";

/** What every cell may need: the page's callbacks, and which Track is playing. */
interface Meta {
  readonly actions: TrackActions;
  readonly playingId: number | undefined;
}

const features = tableFeatures({
  rowSortingFeature,
  columnVisibilityFeature,
  columnSizingFeature,
  columnResizingFeature,
  sortedRowModel: createSortedRowModel(),
  tableMeta: {} as Meta,
});

type Column = ColumnDef<typeof features, Track>;

const WHY: Record<string, string> = {
  offline: "Offline",
  unavailable: "Unavailable",
  missing: "Missing",
  cant_play: "Can't play",
};

const STARS = [1, 2, 3, 4, 5] as const;
const ROW_HEIGHT = 49;
const SAVED = "medleyplay.columns.v1";

/** Compare as people read names: by locale, numbers in order, ignoring case. */
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const byText = (a: Row<typeof features, Track>, b: Row<typeof features, Track>, id: string) =>
  collator.compare(a.getValue<string>(id), b.getValue<string>(id));
const byNumber = (a: Row<typeof features, Track>, b: Row<typeof features, Track>, id: string) =>
  (a.getValue<number | null>(id) ?? -1) - (b.getValue<number | null>(id) ?? -1);

/** What the table does when a Track is chosen, queued, or rated. */
export interface TrackActions {
  /** Play `shown`, the Tracks in the order the table shows them, from its entry `index`. */
  readonly onPlay: (shown: readonly Track[], index: number) => void;
  readonly onPlayNext: (track: Track) => void;
  readonly onAdd: (track: Track) => void;
  readonly onFavorite: (track: Track, favorite: boolean) => void;
  readonly onRate: (track: Track, rating: number | null) => void;
}

/** The columns a browser shows and their widths, as it last left them. */
interface Layout {
  readonly visibility: ColumnVisibilityState;
  readonly sizing: ColumnSizingState;
}

const DEFAULT_LAYOUT: Layout = { visibility: { plays: false, added: false }, sizing: {} };

function savedLayout(): Layout {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(SAVED) ?? "null");
    if (typeof saved === "object" && saved !== null && "visibility" in saved && "sizing" in saved) {
      return saved as Layout;
    }
  } catch {
    // A layout this browser can't read or keep starts from the default.
  }
  return DEFAULT_LAYOUT;
}

function saveLayout(layout: Layout): void {
  try {
    localStorage.setItem(SAVED, JSON.stringify(layout));
  } catch {
    // Best effort: the next visit starts from the default.
  }
}

/** Tracks in a table; with no Tracks, `empty` shows instead. */
export function TrackTable({
  tracks,
  playingId,
  empty,
  actions,
}: {
  readonly tracks: readonly Track[];
  readonly playingId: number | undefined;
  readonly empty: ReactNode;
  readonly actions: TrackActions;
}) {
  const [layout, setLayout] = useState(savedLayout);
  useEffect(() => {
    saveLayout(layout);
  }, [layout]);

  const table = useTable({
    features,
    columns: COLUMNS,
    // The columns stay put, so a new callback or Track playing doesn't sort again.
    meta: { actions, playingId },
    data: tracks,
    getRowId: (track) => String(track.id),
    enableMultiSort: false,
    columnResizeMode: "onChange",
    state: { columnVisibility: layout.visibility, columnSizing: layout.sizing },
    onColumnVisibilityChange: (change) => {
      setLayout((now) => ({
        ...now,
        visibility: typeof change === "function" ? change(now.visibility) : change,
      }));
    },
    onColumnSizingChange: (change) => {
      setLayout((now) => ({
        ...now,
        sizing: typeof change === "function" ? change(now.sizing) : change,
      }));
    },
  });

  const rows = table.getRowModel().rows;
  // The rows scroll with the page, so the virtualizer needs where they start on it.
  const body = useRef<HTMLTableSectionElement>(null);
  const [top, setTop] = useState(0);
  useEffect(() => {
    const element = body.current;
    if (element === null || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => {
      setTop(element.getBoundingClientRect().top + window.scrollY);
    });
    observer.observe(document.body);
    return () => {
      observer.disconnect();
    };
  }, []);
  const virtual = useWindowVirtualizer({
    count: rows.length,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
    scrollMargin: top,
  });
  const items = virtual.getVirtualItems();
  const before = (items[0]?.start ?? top) - top;
  const after = virtual.getTotalSize() - ((items.at(-1)?.end ?? top) - top);
  const visibleColumns = table.getVisibleLeafColumns().length;

  if (tracks.length === 0) {
    return <>{empty}</>;
  }
  return (
    <>
      <div className="table-tools">
        <details className="dropdown columns-menu">
          <summary>
            <SlidersHorizontalIcon weight="regular" aria-hidden />
            Columns
          </summary>
          <ul>
            {table
              .getAllLeafColumns()
              .filter((column) => column.getCanHide())
              .map((column) => (
                <li key={column.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={column.getIsVisible()}
                      onChange={column.getToggleVisibilityHandler()}
                    />
                    {LABELS[column.id]}
                  </label>
                </li>
              ))}
          </ul>
        </details>
      </div>
      <table className="tracks" aria-rowcount={rows.length + 1}>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} aria-rowindex={1}>
              {group.headers.map((header) => {
                const { column } = header;
                const sorted = column.getIsSorted();
                const label = LABELS[column.id] ?? "";
                return (
                  <th
                    key={header.id}
                    scope="col"
                    className={column.id}
                    style={column.id in layout.sizing ? { width: header.getSize() } : undefined}
                    aria-sort={
                      sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                    }
                  >
                    {column.getCanSort() ? (
                      <button
                        type="button"
                        className="sort"
                        onClick={column.getToggleSortingHandler()}
                      >
                        {HIDDEN_LABELS.has(column.id) ? (
                          <span className="visually-hidden">{label}</span>
                        ) : (
                          label
                        )}
                        {sorted === "asc" && <CaretUpIcon weight="bold" aria-hidden />}
                        {sorted === "desc" && <CaretDownIcon weight="bold" aria-hidden />}
                      </button>
                    ) : (
                      <span className="visually-hidden">{label}</span>
                    )}
                    {column.getCanResize() && (
                      <div
                        className={column.getIsResizing() ? "resizer resizing" : "resizer"}
                        // A pointer's or a finger's handle; the Columns menu is for everyone.
                        aria-hidden
                        onMouseDown={header.getResizeHandler()}
                        onTouchStart={header.getResizeHandler()}
                        onDoubleClick={() => {
                          column.resetSize();
                        }}
                      />
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody ref={body}>
          {before > 0 && (
            <tr aria-hidden className="spacer">
              <td colSpan={visibleColumns} style={{ height: before }} />
            </tr>
          )}
          {items.map((item) => {
            const row = rows[item.index];
            if (row === undefined) {
              return null;
            }
            const track = row.original;
            return (
              <tr
                key={row.id}
                ref={virtual.measureElement}
                data-index={item.index}
                aria-rowindex={item.index + 2}
                className={track.availability === "ok" ? undefined : "unplayable"}
                aria-current={track.id === playingId ? "true" : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className={cell.column.id}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            );
          })}
          {after > 0 && (
            <tr aria-hidden className="spacer">
              <td colSpan={visibleColumns} style={{ height: after }} />
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

const LABELS: Record<string, string> = {
  favorite: "Favorite",
  title: "Title",
  artist: "Artist",
  album: "Album",
  time: "Time",
  rating: "Rating",
  plays: "Plays",
  added: "Added",
  actions: "Actions",
};

/** Columns whose header shows an icon's worth of room, so their name is for screen readers. */
const HIDDEN_LABELS = new Set(["favorite"]);

const added = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

const meta = (table: { readonly options: { readonly meta?: Meta } }): Meta => {
  const found = table.options.meta;
  if (found === undefined) {
    throw new Error("The song table's cells need its meta.");
  }
  return found;
};

const COLUMNS: Column[] = [
  {
    id: "favorite",
    accessorFn: (track) => (track.favorite ? 1 : 0),
    sortFn: byNumber,
    sortDescFirst: true,
    enableResizing: false,
    cell: ({ row: { original: track }, table }) => (
      <button
        type="button"
        className={track.favorite ? "icon heart on" : "icon heart"}
        aria-label={`Favorite ${track.title}`}
        aria-pressed={track.favorite}
        title={track.favorite ? "Favorite" : "Not a favorite"}
        onClick={() => {
          meta(table).actions.onFavorite(track, !track.favorite);
        }}
      >
        <HeartIcon weight={track.favorite ? "fill" : "regular"} aria-hidden />
      </button>
    ),
  },
  {
    id: "title",
    accessorKey: "title",
    sortFn: byText,
    enableHiding: false,
    enableResizing: false,
    cell: ({ row, table }) => {
      const track = row.original;
      const playable = track.availability === "ok";
      const { actions, playingId } = meta(table);
      return (
        <div className="title-cell">
          {track.id === playingId && <span className="bars" aria-hidden />}
          <button
            type="button"
            className="title"
            onClick={() => {
              const shown = table.getRowModel().rows;
              actions.onPlay(
                shown.map((each) => each.original),
                shown.indexOf(row),
              );
            }}
            disabled={!playable}
          >
            {track.title}
          </button>
          {!playable && <span className="why">{WHY[track.availability]}</span>}
          <span className="subtitle" aria-hidden>
            {track.artist}
          </span>
        </div>
      );
    },
  },
  { id: "artist", accessorKey: "artist", sortFn: byText, size: 200, minSize: 80 },
  { id: "album", accessorKey: "album", sortFn: byText, size: 200, minSize: 80 },
  {
    id: "time",
    accessorKey: "duration_ms",
    sortFn: byNumber,
    sortDescFirst: false,
    enableResizing: false,
    cell: (info) => formatTime((info.getValue<number | null>() ?? 0) / 1000),
  },
  {
    id: "rating",
    accessorKey: "rating",
    sortFn: byNumber,
    sortDescFirst: false,
    enableResizing: false,
    cell: ({ row: { original: track }, table }) => (
      <fieldset className="stars">
        <legend className="visually-hidden">Rate {track.title}</legend>
        {STARS.map((stars) => (
          <button
            key={stars}
            type="button"
            className="icon star"
            aria-label={stars === 1 ? "1 star" : `${String(stars)} stars`}
            aria-pressed={track.rating === stars}
            onClick={() => {
              meta(table).actions.onRate(track, track.rating === stars ? null : stars);
            }}
          >
            <StarIcon
              weight={track.rating !== null && stars <= track.rating ? "fill" : "light"}
              aria-hidden
            />
          </button>
        ))}
      </fieldset>
    ),
  },
  {
    id: "plays",
    accessorKey: "play_count",
    sortFn: byNumber,
    sortDescFirst: false,
    enableResizing: false,
  },
  {
    id: "added",
    accessorFn: (track) => Date.parse(track.added_at),
    sortFn: byNumber,
    sortDescFirst: false,
    enableResizing: false,
    cell: (info) => added.format(info.getValue<number>()),
  },
  {
    id: "actions",
    enableSorting: false,
    enableHiding: false,
    enableResizing: false,
    cell: ({ row: { original: track }, table }) => {
      const playable = track.availability === "ok";
      const { actions } = meta(table);
      return (
        <>
          <button
            type="button"
            className="icon"
            onClick={() => {
              actions.onPlayNext(track);
            }}
            disabled={!playable}
            aria-label={`Play ${track.title} next`}
            title="Play next"
          >
            <QueueIcon weight="light" aria-hidden />
          </button>
          <button
            type="button"
            className="icon"
            onClick={() => {
              actions.onAdd(track);
            }}
            disabled={!playable}
            aria-label={`Add ${track.title} to the queue`}
            title="Add to the queue"
          >
            <ListPlusIcon weight="light" aria-hidden />
          </button>
        </>
      );
    },
  },
];
