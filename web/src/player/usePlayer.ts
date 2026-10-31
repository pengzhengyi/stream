/**
 * @file The player: one `<audio>` element playing the queue, with the lock screen's controls.
 *
 * A song inside a longer file plays its stretch of that file: the player shows, seeks,
 * and saves its position from the song's own start, and moves on at its end, playing
 * on without reloading the file when the next song starts there.
 */

import { type RefObject, useEffect, useEffectEvent, useReducer, useRef, useState } from "react";

import { ApiError, type PlaybackAnswer, type Track, api } from "../api";
import { newId } from "../ids";
import { PlayTime, countsAsPlayed } from "./playCount";
import { EMPTY, type Entry, type Queue, type Repeat, current, following, reduce } from "./queue";
import { type Play, forgetPlay, keepPlay, keptPlays, loadQueue, saveQueue } from "./storage";
import {
  type Stretch,
  WHOLE,
  fileTimeOf,
  lengthOf,
  positionIn,
  remainingIn,
  stretchOf,
} from "./stretch";
import { loadVolume, saveVolume } from "./volume";

/** What the player is doing. */
export type Status =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "preparing" }
  | { readonly kind: "playing" }
  | { readonly kind: "paused" }
  | { readonly kind: "failed"; readonly message: string };

/** The player as the page sees it. */
export interface Player {
  readonly queue: Queue;
  readonly status: Status;
  readonly shuffled: boolean;
  readonly repeat: Repeat;
  /** Seconds into the current Track. */
  readonly position: number;
  /** The current Track's length in seconds, once known. */
  readonly duration: number | undefined;
  /** How loud it plays, from 0 to 1. */
  readonly volume: number;
  /** Whether it is silent for now; the volume comes back as it was. */
  readonly muted: boolean;
  readonly playList: (tracks: readonly Track[], start: number) => void;
  /** Play every Track of `tracks` from the first, in their order or shuffled. */
  readonly playAll: (tracks: readonly Track[], shuffled: boolean) => void;
  readonly playNext: (track: Track) => void;
  readonly add: (track: Track) => void;
  readonly toggle: () => void;
  readonly next: () => void;
  readonly previous: () => void;
  readonly seek: (seconds: number) => void;
  /** Move an upcoming entry to place `to` among what plays next, 0 being next. */
  readonly move: (key: string, to: number) => void;
  readonly remove: (key: string) => void;
  readonly clear: () => void;
  readonly shuffle: (on: boolean) => void;
  readonly setRepeat: (repeat: Repeat) => void;
  /** Change the volume, and turn the sound back on. */
  readonly setVolume: (volume: number) => void;
  readonly setMuted: (muted: boolean) => void;
}

/** What the page shows about one entry of the queue. */
interface View {
  readonly key: string | undefined;
  readonly status: Status;
  readonly position: number;
  readonly duration: number | undefined;
}

const MAX_PREPARE_ATTEMPTS = 3;
const RESTART_AFTER = 3;
const SAVE_EVERY = 5;
const FINISHED_JOB = new Set(["succeeded", "failed", "cancelled"]);
const PAUSING_ERRORS = new Set(["AbortError", "NotAllowedError"]);
/** How near a song's start the file may already be for it to play on without a seek, in seconds. */
const IN_PLACE = 0.25;
/** The plays the server will never accept, so retrying them is pointless. */
const REFUSED_PLAY = new Set([404, 409, 422]);

const UNPLAYABLE: Record<string, string> = {
  offline: "This Track's Library is offline.",
  unavailable: "This Track is unavailable.",
  missing: "This Track's file is missing.",
  cant_play: "This Track can't be played.",
};

const entryOf = (track: Track): Entry => ({ key: newId(), trackId: track.id });
const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

/**
 * Play the queue through one `<audio>` element, which the page renders once with the
 * returned ref: `<audio ref={audio} />`.
 *
 * `tracks` names each Track for the lock screen; `onSignedOut` runs when a request
 * finds the session has expired.
 */
export function usePlayer(
  tracks: ReadonlyMap<number, Track>,
  onSignedOut: () => void,
): readonly [Player, RefObject<HTMLAudioElement | null>] {
  const audio = useRef<HTMLAudioElement>(null);
  const [queue, dispatch] = useReducer(reduce, EMPTY);
  const [view, setView] = useState<View>({
    key: undefined,
    status: { kind: "idle" },
    position: 0,
    duration: undefined,
  });
  const ahead = useRef(new Map<number, PlaybackAnswer>());
  const loads = useRef(0);
  const playingKey = useRef<string | undefined>(undefined);
  // A restored queue starts paused at its saved position, once its Track's metadata loads.
  const restore = useRef<number | undefined>(undefined);
  const resumeAt = useRef<number | undefined>(undefined);
  const listening = useRef<{ play: Play; time: PlayTime; counted: boolean } | undefined>(undefined);
  const lastSaved = useRef(0);
  // The current song's stretch of its file, the timer that ends it, and the entry last ended.
  const stretch = useRef<Stretch>(WHOLE);
  const ending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const ended = useRef<string | undefined>(undefined);
  const [volume, setVolume] = useState(loadVolume);
  const [muted, setMuted] = useState(false);

  const playing = current(queue);
  const key = playing?.key;
  const trackId = playing?.trackId;

  /** Change what the page shows about the entry `forKey`, ignoring an entry since replaced. */
  const show = (forKey: string | undefined, change: Partial<View>) => {
    setView((now) =>
      now.key === forKey
        ? { ...now, ...change }
        : { key: forKey, status: { kind: "loading" }, position: 0, duration: undefined, ...change },
    );
  };

  const failed = (forKey: string | undefined, error: unknown) => {
    const status = failureOf(error);
    if (status === undefined) {
      onSignedOut();
    } else {
      show(forKey, { status });
    }
  };
  const fail = useEffectEvent(failed);

  /** Start counting a new play of `forTrack`, the Track now starting from its beginning. */
  const startListening = (forTrack: number) => {
    listening.current = {
      play: { id: newId(), trackId: forTrack, playedAt: new Date().toISOString() },
      time: new PlayTime(),
      counted: false,
    };
  };
  const listen = useEffectEvent(startListening);

  // Restore the saved queue paused, and send any plays a closed page left behind.
  useEffect(() => {
    void loadQueue().then((saved) => {
      if (saved !== undefined && saved.queue.entries.length > 0) {
        restore.current = saved.seconds;
        dispatch({ type: "restore", queue: saved.queue });
      }
    });
    void sendPlays();
  }, []);

  // Load the current entry whenever it changes; a later load supersedes an earlier one.
  useEffect(() => {
    const element = audio.current;
    playingKey.current = key;
    if (element === null) {
      return;
    }
    const load = ++loads.current;
    const stale = () => load !== loads.current;
    clearTimeout(ending.current);
    ended.current = undefined;
    if (trackId === undefined) {
      element.pause();
      element.removeAttribute("src");
      element.load();
      return;
    }
    const restoring = restore.current;
    restore.current = undefined;
    resumeAt.current = restoring;
    void (async () => {
      try {
        const answer = await answerFor(trackId, ahead.current, () => {
          if (!stale()) {
            show(key, { status: { kind: "preparing" } });
          }
        });
        if (stale()) {
          return;
        }
        if (answer.state !== "ready") {
          const message =
            answer.state === "unplayable"
              ? (UNPLAYABLE[answer.availability] ?? "This Track can't be played.")
              : "This Track couldn't be prepared.";
          show(key, { status: { kind: "failed", message } });
          return;
        }
        if (element.canPlayType(answer.media_type) === "") {
          show(key, { status: { kind: "failed", message: "This browser can't play this file." } });
          return;
        }
        listen(trackId);
        const song = stretchOf(answer);
        stretch.current = song;
        if (playsFrom(element, answer.audio_url)) {
          // A song of the file already loaded: play on, from its start.
          if (Math.abs(element.currentTime - song.start) > IN_PLACE) {
            element.currentTime = song.start;
          }
          // Playing on fires no `play` event, so the new entry says it is playing itself.
          show(key, {
            duration: lengthOf(song, element.duration),
            ...(element.paused ? {} : { status: { kind: "playing" } }),
          });
          if (element.paused) {
            await element.play();
          }
          return;
        }
        element.src = answer.audio_url;
        if (restoring === undefined) {
          await element.play();
        } else {
          show(key, { status: { kind: "paused" } });
        }
      } catch (error) {
        if (!stale()) {
          fail(key, error);
        }
      }
    })();
    // A new entry for the same Track is a new play, so its key decides.
  }, [key, trackId]);

  const toggle = () => {
    const element = audio.current;
    if (element?.getAttribute("src") == null) {
      return;
    }
    if (element.paused) {
      const forKey = playingKey.current;
      element.play().catch((error: unknown) => {
        failed(forKey, error);
      });
    } else {
      element.pause();
    }
  };
  /** Start the current Track over, as a new play, and play it if `play`. */
  const restart = (play: boolean) => {
    const element = audio.current;
    if (element === null || trackId === undefined) {
      return;
    }
    element.currentTime = stretch.current.start;
    ended.current = undefined;
    startListening(trackId);
    if (play) {
      const forKey = playingKey.current;
      element.play().catch((error: unknown) => {
        failed(forKey, error);
      });
    }
  };
  const previous = () => {
    const element = audio.current;
    if (
      element !== null &&
      (positionIn(stretch.current, element.currentTime) > RESTART_AFTER || queue.position === 0)
    ) {
      restart(false);
      return;
    }
    dispatch({ type: "previous" });
  };
  const next = () => {
    // A queue that starts over on the same entry keeps its key, so it plays again in place.
    if (key !== undefined && following(queue)?.key === key) {
      restart(true);
      return;
    }
    dispatch({ type: "next" });
  };
  const seek = (seconds: number) => {
    const element = audio.current;
    if (element !== null && Number.isFinite(seconds)) {
      element.currentTime = fileTimeOf(stretch.current, seconds, element.duration);
    }
  };

  /** End the current entry once: start it over, or move on, playing on into the next song of the file. */
  const finish = useEffectEvent(() => {
    const element = audio.current;
    if (element === null || ended.current === playingKey.current) {
      return;
    }
    ended.current = playingKey.current;
    clearTimeout(ending.current);
    if (queue.repeat === "one") {
      restart(true);
      return;
    }
    const coming = following(queue);
    const early = coming === undefined ? undefined : ahead.current.get(coming.trackId);
    const end = stretch.current.end;
    const flowsOn =
      early?.state === "ready" &&
      playsFrom(element, early.audio_url) &&
      end !== undefined &&
      Math.abs(stretchOf(early).start - end) <= IN_PLACE;
    if (end !== undefined && !flowsOn) {
      element.pause();
    }
    next();
  });

  const onTime = useEffectEvent((element: HTMLAudioElement) => {
    const position = positionIn(stretch.current, element.currentTime);
    show(playingKey.current, { position });
    const left = remainingIn(stretch.current, element.currentTime);
    if (left !== undefined && !element.paused) {
      // `timeupdate` comes a few times a second; the timer ends the song on time between.
      clearTimeout(ending.current);
      if (left <= 0) {
        finish();
      } else {
        ending.current = setTimeout(finish, (left * 1000) / element.playbackRate);
      }
    }
    const heard = listening.current;
    if (heard !== undefined && !element.paused) {
      heard.time.update(element.currentTime);
      const trackMs = tracks.get(heard.play.trackId)?.duration_ms ?? element.duration * 1000;
      if (!heard.counted && countsAsPlayed(heard.time.playedMs, trackMs)) {
        heard.counted = true;
        void keepPlay(heard.play).then(() => sendPlays(heard.play));
      }
    }
    if (Math.abs(position - lastSaved.current) >= SAVE_EVERY) {
      lastSaved.current = position;
      void saveQueue({ queue, seconds: position });
    }
  });

  const onLoaded = useEffectEvent((element: HTMLAudioElement) => {
    const song = stretch.current;
    if (resumeAt.current !== undefined || song.start > 0) {
      element.currentTime = fileTimeOf(song, resumeAt.current ?? 0, element.duration);
      resumeAt.current = undefined;
    }
    show(playingKey.current, { duration: lengthOf(song, element.duration) });
    updatePositionState(element, song);
  });

  // Follow the audio element.
  useEffect(() => {
    const element = audio.current;
    if (element === null) {
      return;
    }
    const handlers: [string, () => void][] = [
      [
        "play",
        () => {
          show(playingKey.current, { status: { kind: "playing" } });
        },
      ],
      [
        "pause",
        () => {
          clearTimeout(ending.current);
          listening.current?.time.pause();
          if (!element.ended) {
            show(playingKey.current, { status: { kind: "paused" } });
          }
        },
      ],
      [
        "ended",
        () => {
          finish();
        },
      ],
      [
        "loadedmetadata",
        () => {
          onLoaded(element);
        },
      ],
      [
        "timeupdate",
        () => {
          onTime(element);
        },
      ],
      [
        "seeked",
        () => {
          listening.current?.time.pause();
          updatePositionState(element, stretch.current);
        },
      ],
      [
        "error",
        () => {
          if (element.getAttribute("src") === null) {
            return;
          }
          // An expired session answers the audio request 401, which the element can't show.
          const forKey = playingKey.current;
          api.me().then(
            () => {
              show(forKey, { status: { kind: "failed", message: "This Track couldn't play." } });
            },
            (error: unknown) => {
              fail(forKey, error);
            },
          );
        },
      ],
    ];
    for (const [name, handler] of handlers) {
      element.addEventListener(name, handler);
    }
    return () => {
      for (const [name, handler] of handlers) {
        element.removeEventListener(name, handler);
      }
    };
  }, []);

  useEffect(() => {
    if (audio.current !== null) {
      audio.current.volume = volume;
    }
  }, [volume]);
  useEffect(() => {
    if (audio.current !== null) {
      audio.current.muted = muted;
    }
  }, [muted]);

  // Save the queue whenever it changes.
  useEffect(() => {
    lastSaved.current = 0;
    void saveQueue({ queue, seconds: 0 });
  }, [queue]);

  // The lock screen: the Track's details, and only the controls iOS shows as buttons.
  const track = trackId === undefined ? undefined : tracks.get(trackId);
  const status: Status =
    key === undefined ? { kind: "idle" } : view.key === key ? view.status : { kind: "loading" };

  // Once the current Track is ready, ask how the next plays, again whenever the next changes.
  const loaded = status.kind === "playing" || status.kind === "paused";
  const coming = following(queue);
  const comingKey = coming?.key;
  const comingTrack = coming?.trackId;
  useEffect(() => {
    if (loaded && comingTrack !== undefined && comingKey !== key) {
      void lookAhead(comingTrack, ahead.current);
    }
  }, [loaded, key, comingKey, comingTrack]);
  useEffect(() => {
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata =
        track === undefined
          ? null
          : new MediaMetadata({ title: track.title, artist: track.artist, album: track.album });
    }
  }, [track]);
  useEffect(() => {
    if ("mediaSession" in navigator) {
      navigator.mediaSession.playbackState =
        status.kind === "playing" ? "playing" : status.kind === "paused" ? "paused" : "none";
    }
  }, [status.kind]);
  const onAction = useEffectEvent((details: MediaSessionActionDetails) => {
    switch (details.action) {
      case "play":
      case "pause":
        toggle();
        break;
      case "previoustrack":
        previous();
        break;
      case "nexttrack":
        next();
        break;
      default:
        if (details.seekTime !== undefined) {
          seek(details.seekTime);
        }
    }
  });
  useEffect(() => {
    if (!("mediaSession" in navigator)) {
      return;
    }
    const actions: MediaSessionAction[] = ["play", "pause", "previoustrack", "nexttrack", "seekto"];
    for (const action of actions) {
      navigator.mediaSession.setActionHandler(action, onAction);
    }
    return () => {
      for (const action of actions) {
        navigator.mediaSession.setActionHandler(action, null);
      }
    };
  }, []);

  const shown = view.key === key ? view : undefined;
  const player: Player = {
    queue,
    status,
    shuffled: queue.order !== undefined,
    repeat: queue.repeat,
    position: shown?.position ?? 0,
    duration: shown?.duration,
    volume,
    muted,
    playList: (list, start) => {
      dispatch({ type: "play", entries: list.map(entryOf), start, random: Math.random });
    },
    playAll: (list, shuffled) => {
      dispatch({ type: "playAll", entries: list.map(entryOf), shuffled, random: Math.random });
    },
    playNext: (chosen) => {
      dispatch({ type: "playNext", entry: entryOf(chosen) });
    },
    add: (chosen) => {
      dispatch({ type: "add", entry: entryOf(chosen) });
    },
    toggle,
    next,
    previous,
    seek,
    move: (moving, to) => {
      dispatch({ type: "move", key: moving, to });
    },
    remove: (removing) => {
      dispatch({ type: "remove", key: removing });
    },
    clear: () => {
      dispatch({ type: "clear" });
    },
    shuffle: (on) => {
      dispatch(on ? { type: "shuffle", random: Math.random } : { type: "unshuffle" });
    },
    setRepeat: (repeat) => {
      dispatch({ type: "repeat", repeat });
    },
    setVolume: (chosen) => {
      const within = Math.min(Math.max(chosen, 0), 1);
      setVolume(within);
      setMuted(false);
      saveVolume(within);
    },
    setMuted,
  };
  return [player, audio];
}

/** Return the status to show for `error`, or `undefined` when the session has expired. */
function failureOf(error: unknown): Status | undefined {
  if (error instanceof ApiError && error.status === 401) {
    return undefined;
  }
  // `play()` refused before a tap, or interrupted by a pause, leaves the Track paused.
  if (error instanceof DOMException && PAUSING_ERRORS.has(error.name)) {
    return { kind: "paused" };
  }
  return { kind: "failed", message: error instanceof Error ? error.message : String(error) };
}

/**
 * Return how `trackId` plays, using an answer asked for ahead of time when there is one.
 *
 * A Track that must be prepared waits for its Job, then asks again, a few times at most.
 */
async function answerFor(
  trackId: number,
  ahead: Map<number, PlaybackAnswer>,
  onPreparing: () => void,
): Promise<PlaybackAnswer> {
  const early = ahead.get(trackId);
  ahead.delete(trackId);
  let answer = early?.state === "ready" ? early : await api.playback(trackId);
  for (
    let attempt = 1;
    answer.state === "preparing" && attempt <= MAX_PREPARE_ATTEMPTS;
    attempt++
  ) {
    onPreparing();
    const job = await finishedJob(answer.job_id);
    if (job.state !== "succeeded") {
      throw new Error(job.failure_message || `Preparing this Track was ${job.state}.`);
    }
    answer = await api.playback(trackId);
  }
  return answer;
}

async function finishedJob(jobId: number) {
  for (let polls = 0; ; polls++) {
    await wait(polls < 5 ? 1000 : 3000);
    const job = await api.job(jobId);
    if (FINISHED_JOB.has(job.state)) {
      return job;
    }
  }
}

/** Ask now how `trackId` plays, so `ended` only swaps the source; it starts preparing too. */
async function lookAhead(trackId: number, ahead: Map<number, PlaybackAnswer>): Promise<void> {
  if (ahead.has(trackId)) {
    return;
  }
  try {
    ahead.set(trackId, await api.playback(trackId));
  } catch {
    // The next Track asks again when its turn comes.
  }
}

/** Send every kept play, forgetting those the server accepted or will always refuse. */
async function sendPlays(only?: Play): Promise<void> {
  const plays = only === undefined ? await keptPlays() : [only];
  for (const play of plays) {
    try {
      await api.recordPlay(play.id, play.trackId, play.playedAt);
      await forgetPlay(play.id);
    } catch (error) {
      if (error instanceof ApiError && REFUSED_PLAY.has(error.status)) {
        await forgetPlay(play.id);
      }
    }
  }
}

/** Return whether `element` already has the file at `audioUrl` loaded. */
function playsFrom(element: HTMLAudioElement, audioUrl: string): boolean {
  return (
    element.getAttribute("src") !== null && element.src === new URL(audioUrl, document.baseURI).href
  );
}

function updatePositionState(element: HTMLAudioElement, song: Stretch): void {
  const duration = lengthOf(song, element.duration);
  // `setPositionState` throws on an unknown length, which a live stream has.
  if (!("mediaSession" in navigator) || duration === undefined) {
    return;
  }
  navigator.mediaSession.setPositionState({
    duration,
    playbackRate: element.playbackRate,
    position: Math.min(positionIn(song, element.currentTime), duration),
  });
}
