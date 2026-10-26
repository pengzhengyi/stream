import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { applyTheme } from "../theme";
import { ThemeSwitch } from "./ThemeSwitch";

afterEach(() => {
  applyTheme("system");
  localStorage.clear();
});

describe("the theme switch", () => {
  it("shows the theme chosen in any switch on the page", async () => {
    render(
      <>
        <ThemeSwitch />
        <ThemeSwitch />
      </>,
    );

    await userEvent.click(screen.getAllByRole("radio", { name: "Dark" })[0] ?? document.body);

    for (const dark of screen.getAllByRole("radio", { name: "Dark" })) {
      expect(dark).toHaveAttribute("aria-checked", "true");
    }
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
