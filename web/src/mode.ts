/**
 * @file The Mode in words: why medleyplay is Offline, and the network it is on.
 */

import type { Mode, ModeSetting } from "./api";

/** Return why the Mode is Offline, such as "on a metered network", or `null` while Online. */
export function offlineBecause(mode: Mode): string | null {
  if (mode.online) {
    return null;
  }
  switch (mode.reason) {
    case "set_offline":
      return "set to Always Offline";
    case "no_network":
      return "no network";
    case "metered":
      return "on a metered network";
    case "unknown_network":
      return "can't tell which network this is";
    case "settling":
      return "waiting for the network to settle";
    case "unreachable":
    case "online":
    case "set_online":
      return "the internet can't be reached";
  }
}

/** Return the network the server is on, in a sentence. */
export function networkSaid(mode: Mode): string {
  const { network } = mode;
  if (network === null) {
    return mode.reason === "no_network" ? "No network." : "The network can't be read here.";
  }
  const on = { wifi: "On Wi-Fi", wired: "On a cable", unknown: "On a network" }[network.kind];
  return network.metered_as === null
    ? `${on}.`
    : `${on}, marked metered as “${network.metered_as}”.`;
}

/** Each setting, as Settings offers it. */
export const SETTINGS: readonly { readonly setting: ModeSetting; readonly said: string }[] = [
  {
    setting: "auto",
    said: "Auto: Online unless there is no network, it is marked metered, or the internet can't be reached",
  },
  { setting: "online", said: "Always Online" },
  { setting: "offline", said: "Always Offline: nothing contacts a music site" },
];
