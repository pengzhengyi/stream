import { expect, test } from "@playwright/test";

test("the page loads and shows the title", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("stream");
  await expect(page.getByRole("heading", { level: 1, name: "stream" })).toBeVisible();
});
