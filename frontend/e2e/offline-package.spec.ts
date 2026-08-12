import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { readFileSync, rmSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const repositoryRoot = path.resolve(process.cwd(), "..");
const fixtureRoot = path.join("/tmp", `exam-prep-offline-e2e-${process.pid}`);

test.beforeAll(() => {
  execFileSync(
    "python3",
    [path.join(repositoryRoot, "backend/scripts/build_offline_e2e_fixture.py"), fixtureRoot],
    {
      env: {
        ...process.env,
        PYTHONPATH: path.join(repositoryRoot, "backend/src")
      }
    }
  );
});

test.afterAll(() => {
  rmSync(fixtureRoot, { force: true, recursive: true });
});

test("flashcards work and persist without network access", async ({ page }) => {
  const networkRequests: string[] = [];
  page.on("request", (request) => {
    if (/^https?:/.test(request.url())) {
      networkRequests.push(request.url());
    }
  });
  page.on("dialog", (dialog) => dialog.accept());

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(pathToFileURL(path.join(fixtureRoot, "flashcards.html")).href);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  const firstPrompt = page.getByRole("heading", { name: "What risk does beta measure in CAPM?" });
  await expect(firstPrompt).toBeVisible();
  const firstPromptBounds = await firstPrompt.boundingBox();
  expect(firstPromptBounds?.y).toBeLessThan(844);
  const search = page.getByRole("searchbox", { name: "Search" });
  await search.fill("capm");
  await search.press("ArrowRight");
  await expect(page.getByRole("heading", { name: "What risk does beta measure in CAPM?" })).toBeVisible();
  await search.press("Space");
  await expect(search).toHaveValue("capm ");
  await search.fill("");
  await expect(page.getByRole("button", { name: "Import progress" })).toBeVisible();
  const previousBounds = await page.getByRole("button", { name: "Previous card" }).boundingBox();
  const nextBounds = await page.getByRole("button", { name: "Next card" }).boundingBox();
  expect(previousBounds?.width).toBeGreaterThanOrEqual(44);
  expect(nextBounds?.width).toBeGreaterThanOrEqual(44);
  await page.getByRole("button", { name: "Show answer" }).click();
  await expect(page.getByText(/systematic risk relative to the market portfolio/i)).toBeVisible();
  await page.getByRole("button", { name: "Next card" }).click();
  await expect(page.getByText("2 / 2")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: /one-day 99% VaR/i })).toBeVisible();
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("1 / 2")).toBeVisible();
  expect(networkRequests).toEqual([]);
});

test("mock exam restores an attempt, saves completed HTML, and reopens offline", async ({ browser, page }) => {
  const networkRequests: string[] = [];
  page.on("request", (request) => {
    if (/^https?:/.test(request.url())) {
      networkRequests.push(request.url());
    }
  });
  page.on("dialog", (dialog) => dialog.accept());

  await page.goto(pathToFileURL(path.join(fixtureRoot, "mock-exam.html")).href);
  await expect(page.getByText("05:00")).toBeVisible();
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.getByLabel(/systematic exposure is 40% greater/i).check();
  await expect(page.getByText("1 / 2 answered")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel(/systematic exposure is 40% greater/i)).toBeChecked();
  await page.getByRole("button", { name: "Submit exam" }).click();
  await expect(page.getByText("1 / 2 (50%)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Explanation" })).toBeVisible();
  await expect(page.getByText(/Beta measures systematic exposure/i)).toBeVisible();
  await expect(page.getByText("FRM Book 1, page 42")).toBeVisible();

  const completedPath = path.join(fixtureRoot, "completed-exam.html");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save completed exam" }).click();
  const download = await downloadPromise;
  await download.saveAs(completedPath);
  expect(readFileSync(completedPath, "utf8")).toContain('id="attempt-data"');

  const freshContext = await browser.newContext();
  const completedPage = await freshContext.newPage();
  const completedNetworkRequests: string[] = [];
  completedPage.on("request", (request) => {
    if (/^https?:/.test(request.url())) {
      completedNetworkRequests.push(request.url());
    }
  });
  await completedPage.goto(pathToFileURL(completedPath).href);
  await expect(completedPage.getByText("1 / 2 (50%)")).toBeVisible();
  await expect(completedPage.getByText(/Beta measures systematic exposure/i)).toBeVisible();
  expect(completedNetworkRequests).toEqual([]);
  await freshContext.close();

  await page.getByRole("button", { name: "New attempt" }).click();
  await expect(page.getByRole("button", { name: "Start exam" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  expect(networkRequests).toEqual([]);
});
