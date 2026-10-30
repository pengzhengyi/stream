/**
 * @file Adds the Testing Library matchers to Vitest, stands in for media playback, pointer
 * capture, and dialogs, and unmounts between tests.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

import { forgetBindings } from "./shortcuts";

// The first render of a file loads its modules; in a full run, beside every other
// file, that can take longer than the default second the `find` queries wait.
configure({ asyncUtilTimeout: 5000 });

// jsdom has media elements but can't play them; Playwright tests real playback.
HTMLMediaElement.prototype.load = () => undefined;
HTMLMediaElement.prototype.pause = () => undefined;
HTMLMediaElement.prototype.play = () => Promise.resolve();
HTMLMediaElement.prototype.canPlayType = () => "maybe";
// jsdom has no layout, so there is nothing to scroll.
Element.prototype.scrollIntoView = () => undefined;
// jsdom dispatches pointer events but can't capture the pointer.
Element.prototype.setPointerCapture = () => undefined;
Element.prototype.releasePointerCapture = () => undefined;
// jsdom has `<dialog>` but not its methods: these open and close it as a browser would.
HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
  this.open = true;
  // As a browser does, focus moves to the first control in it.
  this.querySelector<HTMLElement>("[autofocus], button, a[href], input, select, textarea")?.focus();
};
HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
  if (this.open) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  }
};

afterEach(() => {
  cleanup();
  // The shortcuts live in one place for the whole page; each test is a new page.
  forgetBindings();
});
