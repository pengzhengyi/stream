import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VolumeControl } from "./VolumeControl";

describe("the volume", () => {
  it.each([
    ["Volume down", 0.4],
    ["Volume up", 0.6],
  ])("moves one mark with %s", async (button, volume) => {
    const onVolume = vi.fn();
    render(<VolumeControl volume={0.5} onVolume={onVolume} />);

    await userEvent.click(screen.getByRole("button", { name: button }));

    expect(onVolume).toHaveBeenCalledExactlyOnceWith(volume);
  });

  it("follows a drag without changing the volume, then changes it once on letting go", () => {
    const onVolume = vi.fn();
    render(<VolumeControl volume={0.5} onVolume={onVolume} />);
    const bar = screen.getByRole("slider", { name: "Volume" });

    fireEvent.input(bar, { target: { value: "0.3" } });
    fireEvent.input(bar, { target: { value: "0.2" } });

    expect(onVolume).not.toHaveBeenCalled();
    expect(bar).toHaveAttribute("aria-valuetext", "20%");

    fireEvent.change(bar, { target: { value: "0.2" } });

    expect(onVolume).toHaveBeenCalledExactlyOnceWith(0.2);
    expect(bar).toHaveAttribute("aria-valuetext", "50%");
  });
});
