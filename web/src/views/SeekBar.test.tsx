import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { SeekBar } from "./SeekBar";

/** A bar 200 pixels wide from the page's left edge, so each pixel is half a second of 100. */
function renderBar(position = 10) {
  const onSeek = vi.fn();
  const view = render(<SeekBar position={position} duration={100} onSeek={onSeek} />);
  const bar = screen.getByRole("slider", { name: "Position" });
  bar.getBoundingClientRect = () => new DOMRect(0, 0, 200, 12);
  return { onSeek, bar, ...view };
}

const tipOf = (bar: HTMLElement) => bar.querySelector(".seek-tip")?.textContent;

describe("the seek bar", () => {
  it("shows the time under the pointer while hovering, and nothing once it leaves", () => {
    const { bar, onSeek } = renderBar();

    fireEvent.pointerMove(bar, { clientX: 50 });

    expect(tipOf(bar)).toBe("0:25");
    fireEvent.pointerLeave(bar);
    expect(tipOf(bar)).toBeUndefined();
    expect(onSeek).not.toHaveBeenCalled();
  });

  it("seeks where it is clicked, at once", () => {
    const { bar, onSeek } = renderBar();

    fireEvent.pointerDown(bar, { clientX: 100, button: 0 });
    fireEvent.pointerUp(bar, { clientX: 100, button: 0 });

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(50);
  });

  it("follows a drag without seeking, then seeks once where it is let go", () => {
    const { bar, onSeek } = renderBar();

    fireEvent.pointerDown(bar, { clientX: 20, button: 0 });
    fireEvent.pointerMove(bar, { clientX: 60 });
    fireEvent.pointerMove(bar, { clientX: 150 });

    expect(onSeek).not.toHaveBeenCalled();
    expect(bar).toHaveAttribute("aria-valuenow", "75");
    expect(tipOf(bar)).toBe("1:15");

    fireEvent.pointerUp(bar, { clientX: 150, button: 0 });

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(75);
  });

  it("stays where it was sent until the audio gets there, rather than jumping back", () => {
    const { bar, rerender } = renderBar(10);

    fireEvent.pointerDown(bar, { clientX: 100, button: 0 });
    fireEvent.pointerUp(bar, { clientX: 100, button: 0 });
    rerender(<SeekBar position={10.2} duration={100} onSeek={vi.fn()} />);

    expect(bar).toHaveAttribute("aria-valuenow", "50");
    rerender(<SeekBar position={50.1} duration={100} onSeek={vi.fn()} />);
    rerender(<SeekBar position={51} duration={100} onSeek={vi.fn()} />);
    expect(bar).toHaveAttribute("aria-valuenow", "51");
  });

  it("goes back to the audio's position when the audio never gets where it was sent", () => {
    vi.useFakeTimers();
    try {
      const { bar } = renderBar(10);

      fireEvent.pointerDown(bar, { clientX: 100, button: 0 });
      fireEvent.pointerUp(bar, { clientX: 100, button: 0 });
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      expect(bar).toHaveAttribute("aria-valuenow", "10");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps a drag past either end at that end", () => {
    const { bar, onSeek } = renderBar();

    fireEvent.pointerDown(bar, { clientX: 20, button: 0 });
    fireEvent.pointerUp(bar, { clientX: 260, button: 0 });
    fireEvent.pointerDown(bar, { clientX: 20, button: 0 });
    fireEvent.pointerUp(bar, { clientX: -40, button: 0 });

    expect(onSeek.mock.calls).toEqual([[100], [0]]);
  });

  it("forgets a drag the browser cancels, without seeking", () => {
    const { bar, onSeek } = renderBar();

    fireEvent.pointerDown(bar, { clientX: 20, button: 0 });
    fireEvent.pointerCancel(bar);

    expect(onSeek).not.toHaveBeenCalled();
    expect(bar).toHaveAttribute("aria-valuenow", "10");
  });

  it.each([
    ["{ArrowRight}", 15],
    ["{ArrowLeft}", 5],
    ["{PageUp}", 20],
    ["{Home}", 0],
    ["{End}", 100],
  ])("moves with %s at once", async (key, seconds) => {
    const { bar, onSeek } = renderBar();
    bar.focus();

    await userEvent.keyboard(key);

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(seconds);
  });

  it("moves from where the last key sent it, before the audio gets there", async () => {
    const { bar, onSeek } = renderBar();
    bar.focus();

    await userEvent.keyboard("{End}{ArrowLeft}{ArrowLeft}");

    expect(onSeek.mock.calls).toEqual([[100], [95], [90]]);
  });

  it("says where it is, and how long the Track is", () => {
    const { bar } = renderBar(75);

    expect(bar).toHaveAttribute("aria-valuetext", "1:15 of 1:40");
    expect(within(bar).queryByText(/./)).toBeNull();
  });

  it("can't be moved before the Track's length is known", async () => {
    const onSeek = vi.fn();
    render(<SeekBar position={0} duration={undefined} onSeek={onSeek} />);
    const bar = screen.getByRole("slider", { name: "Position" });

    fireEvent.pointerDown(bar, { clientX: 100, button: 0 });
    fireEvent.pointerUp(bar, { clientX: 100, button: 0 });
    bar.focus();
    await userEvent.keyboard("{End}");

    expect(bar).toHaveAttribute("aria-disabled", "true");
    expect(onSeek).not.toHaveBeenCalled();
  });
});
