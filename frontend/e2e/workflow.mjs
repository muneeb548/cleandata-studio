/**
 * End-to-end test of the full CleanData Studio workflow in a real browser,
 * against a running frontend + backend.
 *
 *   1. start the backend  (uvicorn app.main:app --port 8000)
 *   2. start the frontend (npm run dev)
 *   3. npx playwright install chromium   (first time only)
 *   4. npm run e2e                        (E2E_URL defaults to http://localhost:5173)
 *
 * The expected results are computed independently in this file from the test
 * dataset, so the test checks that the downloaded files contain the real
 * cleaned data — not just that the UI says "success".
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const BASE = (process.env.E2E_URL ?? "http://localhost:5173").replace(/\/$/, "");
const HEADLESS = process.env.E2E_HEADED !== "1";
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cleandata-e2e-"));

// ------------------------------------------------------------------ test data
// 120 rows with: padded text, inconsistent case, missing values and 5 exact duplicates (after trimming: 6).
const header = ["id", "name", "city", "amount"];
const cities = ["Lahore", "lahore", " Karachi ", "Islamabad"];
const rows = [];
for (let i = 1; i <= 115; i++) {
  rows.push([String(1000 + i), i % 7 === 0 ? `  Name ${i} ` : `Name ${i}`, cities[i % 4], i % 9 === 0 ? "" : String(100 + i)]);
}
for (const i of [3, 10, 20, 30, 40]) rows.push([...rows[i]]); // exact duplicates
const toCsv = (h, r) => [h, ...r].map((x) => x.join(",")).join("\n") + "\n";
const ORIGINAL = toCsv(header, rows);
const csvPath = path.join(tmp, "e2e_customers.csv");
fs.writeFileSync(csvPath, ORIGINAL);

// Independent expectations
const trimCell = (v) => v.trim();
const TRIMMED = rows.map((r) => r.map(trimCell));
const dedupe = (rs) => {
  const seen = new Set();
  return rs.filter((r) => (seen.has(r.join("\u0001")) ? false : seen.add(r.join("\u0001"))));
};
const TRIMMED_DEDUPED = dedupe(TRIMMED);
const EXPECT = {
  rows: rows.length,
  missing: rows.filter((r) => r[3] === "").length,
  duplicates: rows.length - dedupe(rows).length,
  trimmedCells: rows.flat().filter((v) => v !== v.trim()).length,
  removedAfterTrim: TRIMMED.length - TRIMMED_DEDUPED.length,
};

// ------------------------------------------------------------------ helpers
const results = [];
async function step(name, fn) {
  const t = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - t });
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.push({ name, ok: false, error: err });
    console.log(`  ✗ ${name}\n    ${String(err.message).split("\n")[0]}`);
    throw err;
  }
}
const parseCsv = (text) => text.replace(/\n$/, "").split("\n").map((l) => l.split(","));

async function download(page, label = "Download CSV") {
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: label, exact: true }).click()]);
  const file = path.join(tmp, `${Date.now()}_${dl.suggestedFilename()}`);
  await dl.saveAs(file);
  return { name: dl.suggestedFilename(), text: fs.readFileSync(file, "utf8") };
}

// ------------------------------------------------------------------ run
const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
const nav = (name) => page.locator("nav[aria-label=Workspace]:visible").getByRole("button", { name }).first().click();
const apply = () => page.getByRole("button", { name: "Apply", exact: true }).click();
const preview = () => page.getByRole("button", { name: "Preview", exact: true }).click();

console.log(`CleanData Studio e2e against ${BASE}\nexpected: ${JSON.stringify(EXPECT)}`);
try {
  await step("landing page → Start Cleaning opens the workspace", async () => {
    await page.goto(BASE + "/");
    await page.getByRole("link", { name: "Start Cleaning" }).first().click();
    await page.waitForURL(/\/app$/);
    await page.getByText("No file uploaded yet").waitFor();
  });

  await step("invalid file shows a clear error", async () => {
    const bad = path.join(tmp, "notes.pdf");
    fs.writeFileSync(bad, "%PDF-1.4");
    await page.setInputFiles("input[type=file]", bad);
    await page.getByRole("alert").filter({ hasText: "not a supported data file" }).waitFor();
  });

  await step("upload CSV → real profile is displayed", async () => {
    await page.setInputFiles("input[type=file]", csvPath);
    await page.getByText("Detected issues").waitFor({ timeout: 30_000 });
    const card = (label) => page.locator("section[aria-label='Dataset overview'] > div", { hasText: label }).first();
    assert.match(await card("Total rows").innerText(), new RegExp(`\\b${EXPECT.rows}\\b`));
    assert.match(await card("Missing cells").innerText(), new RegExp(`\\b${EXPECT.missing}\\b`));
    assert.match(await card("Duplicate rows").innerText(), new RegExp(`\\b${EXPECT.duplicates}\\b`));
    assert.ok(await page.getByText("e2e_customers.csv").first().isVisible());
  });

  await step("data preview: pagination and search use the backend", async () => {
    await nav("Data preview");
    await page.getByLabel("Rows per page").selectOption("50");
    await page.getByText(`Showing 1–50 of ${EXPECT.rows} rows`).waitFor();
    await page.getByRole("button", { name: "Next page" }).click();
    await page.getByText(`Showing 51–100 of ${EXPECT.rows} rows`).waitFor();
    await page.getByLabel("Search all columns").fill("Name 77");
    await page.getByText(/Showing 1–1 of 1 rows/).waitFor();
    await page.getByRole("button", { name: "Clear search" }).click();
  });

  await step("cleaning form validation: column required, incompatible column blocked", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: "Missing values" }).click();
    await page.getByText("Select at least one column.").waitFor();
    assert.ok(await page.getByRole("button", { name: "Preview", exact: true }).isDisabled());
    await page.getByLabel("Action").selectOption("fill_mean");
    assert.ok(await page.getByLabel(/city/).isDisabled(), "text column must not be selectable for mean");
  });

  await step("blocked conversion is explained, nothing applied", async () => {
    await page.getByRole("button", { name: "Data types" }).click();
    await page.getByLabel(/^name/).check();
    await preview();
    await page.getByText("This operation cannot be applied as configured").waitFor();
    assert.ok(await page.getByRole("button", { name: "Apply", exact: true }).isDisabled());
  });

  await step("trim whitespace: preview → apply → dashboard refreshes, history updated", async () => {
    await page.getByRole("button", { name: "Text cleaning" }).click();
    await page.getByRole("radio", { name: "Trim spaces" }).click();
    await preview();
    await page.getByText(`If applied: Trimmed spaces in ${EXPECT.trimmedCells} cells.`).waitFor();
    await apply();
    await page.getByText("The working data has been updated").waitFor();
    await page.getByText("1. Trim whitespace").first().waitFor();
    await nav("Overview");
    const dup = await page.locator("section[aria-label='Dataset overview'] > div", { hasText: "Duplicate rows" }).innerText();
    assert.match(dup, new RegExp(`\\b${EXPECT.removedAfterTrim}\\b`), "duplicates must be recalculated after trimming");
  });

  await step("remove duplicates requires preview + confirmation", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: "Duplicates" }).click();
    await preview();
    await page.getByText(`Rows to be removed`).waitFor();
    await apply();
    await page.getByRole("dialog").getByText("Remove data from the working dataset?").waitFor();
    await page.getByRole("button", { name: "Yes, apply" }).click();
    await page.getByText("The working data has been updated").waitFor();
    await page.getByText("2. Remove duplicate rows").first().waitFor();
  });

  await step("compare shows real before/after numbers", async () => {
    await nav("Compare");
    await page.getByText("Row comparison").waitFor();
    const removed = await page.locator("section[aria-label='Change summary'] > div", { hasText: "Rows removed" }).innerText();
    assert.match(removed, new RegExp(`\\b${EXPECT.removedAfterTrim}\\b`));
    await page.getByText("Removed", { exact: true }).first().waitFor();
  });

  await step("download contains the actual cleaned dataset", async () => {
    await nav("Download");
    const { name, text } = await download(page);
    assert.equal(name, "e2e_customers_cleaned.csv");
    assert.deepEqual(parseCsv(text), [header, ...TRIMMED_DEDUPED]);
  });

  await step("undo restores the previous state (trimmed, not deduplicated)", async () => {
    await page.getByRole("button", { name: "Undo last operation" }).click();
    await page.getByText("Last operation undone").waitFor();
    const { text } = await download(page);
    assert.deepEqual(parseCsv(text), [header, ...TRIMMED]);
  });

  await step("reset restores the original upload exactly", async () => {
    await page.getByRole("button", { name: "Reset to original data" }).click();
    await page.getByRole("button", { name: "Reset data" }).click();
    await page.getByText("Dataset reset to the original upload").waitFor();
    const { text } = await download(page);
    assert.equal(text, ORIGINAL);
    assert.ok(await page.getByRole("button", { name: "Undo last operation" }).isDisabled());
  });

  await step("stale preview is rejected by the server and explained", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: "Duplicates" }).click();
    await preview();
    await page.getByText("Rows to be removed").waitFor();
    // Change the data behind the UI's back (as another tab would), then try to apply the old preview.
    const token = await page.evaluate(() => sessionStorage.getItem("cleandata.session"));
    const op = { type: "standardize_text", columns: ["city"], case: "upper" };
    const r = await page.request.post(BASE + "/api/operations/apply", { headers: { "X-Session-Id": token }, data: { operation: op } });
    assert.equal(r.status(), 200);
    await apply();
    await page.getByRole("button", { name: "Yes, apply" }).click();
    await page.getByText("The operation was not applied").waitFor();
    await page.getByText("Your data was not changed.").waitFor();
    await page.getByRole("button", { name: "Preview again" }).waitFor();
  });

  await step("server unreachable: clear message instead of a broken page", async () => {
    await page.route("**/api/**", (route) => route.abort("connectionrefused"));
    await nav("Overview");
    await page.getByText("Cannot reach the CleanData Studio server.").first().waitFor();
    await page.unroute("**/api/**");
    await page.getByRole("button", { name: "Retry" }).first().click();
    await page.getByText("Detected issues").waitFor();
  });

  await step("expired session returns to upload with an explanation", async () => {
    const token = await page.evaluate(() => sessionStorage.getItem("cleandata.session"));
    const res = await page.request.delete(BASE + "/api/session", { headers: { "X-Session-Id": token } });
    assert.equal(res.status(), 204);
    await nav("Data preview"); // any request now finds the session gone
    await page.getByText("Session ended").waitFor();
    await page.getByText("No file uploaded yet").waitFor();
  });

  await step("replace file deletes the session and returns to upload", async () => {
    await page.setInputFiles("input[type=file]", csvPath);
    await page.getByText("Detected issues").waitFor();
    const token = await page.evaluate(() => sessionStorage.getItem("cleandata.session"));
    await page.getByRole("button", { name: "Replace file" }).click();
    await page.getByRole("button", { name: "Delete and upload new file" }).click();
    await page.getByText("No file uploaded yet").waitFor();
    const res = await page.request.get(BASE + "/api/session", { headers: { "X-Session-Id": token } });
    assert.equal(res.status(), 404, "old session must be deleted on the server");
  });

  await step("no JavaScript errors", async () => assert.deepEqual(consoleErrors, []));
} catch {
  /* reported below */
} finally {
  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} steps passed${failed.length ? "" : " — full workflow verified"}`);
  process.exitCode = failed.length ? 1 : 0;
}
