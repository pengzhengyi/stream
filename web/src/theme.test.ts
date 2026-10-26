import { afterEach, describe, expect, it } from "vitest";

import { applyTheme, savedTheme } from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("the theme", () => {
  it("follows the system until a browser chooses one", () => {
    expect(savedTheme()).toBe("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("forces the theme chosen, and remembers it", () => {
    applyTheme("dark");

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(savedTheme()).toBe("dark");
  });

  it("goes back to following the system", () => {
    applyTheme("light");

    applyTheme("system");

    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(savedTheme()).toBe("system");
  });

  it("ignores a saved value it doesn't know", () => {
    localStorage.setItem("medleyplay.theme", "sepia");

    expect(savedTheme()).toBe("system");
  });
});
