/**
 * @file Adds the Testing Library matchers to Vitest, stands in for media playback, and
 * unmounts between tests.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has media elements but can't play them; Playwright tests real playback.
HTMLMediaElement.prototype.load = () => undefined;
HTMLMediaElement.prototype.pause = () => undefined;
HTMLMediaElement.prototype.play = () => Promise.resolve();
HTMLMediaElement.prototype.canPlayType = () => "maybe";

afterEach(() => {
  cleanup();
});
