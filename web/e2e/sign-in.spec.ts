import { expect, test } from "@playwright/test";

import { ALICE } from "./fixtures";

test.use({ storageState: { cookies: [], origins: [] } });

test("signing in shows the Library, and signing out returns to the form", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("medleyplay");

  await page.getByLabel("Username").fill(ALICE.username);
  await page.getByLabel("Password").fill(ALICE.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Alpha", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
});

test("a wrong password is refused with the reason", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Username").fill(ALICE.username);
  await page.getByLabel("Password").fill("not it");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("The username or password is wrong.");
});
