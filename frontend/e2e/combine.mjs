/**
 * End-to-end test of Clean data → Combine files in a real browser, against a running
 * frontend + backend (same setup as workflow.mjs):
 *
 *   E2E_URL=http://localhost:5173 node e2e/combine.mjs
 *
 * Covers: adding a second file, join (like VLOOKUP) with preview → apply → download,
 * undo, append with a source column, inner join confirmation, and removing the file.
 * The expected downloads are written out in this file, so the test checks real data.
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const BASE = (process.env.E2E_URL ?? "http://localhost:5173").replace(/\/$/, "");
const HEADLESS = process.env.E2E_HEADED !== "1";
const SHOTS = process.env.E2E_SCREENSHOTS; // optional folder for screenshots
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cleandata-e2e-combine-"));

const write = (name, text) => {
  const p = path.join(tmp, name);
  fs.writeFileSync(p, text);
  return p;
};
const CUSTOMERS = "id,name,email\n1,Ali,ALI@x.com\n2,Sara,sara@x.com\n3,Omar,\n4,Zoya,zoya@x.com\n";
const customersPath = write("customers.csv", CUSTOMERS);
const ordersPath = write("orders.csv", "Email,amount,city\nali@x.com ,100,Lahore\nsara@x.com,50,Karachi\nsara@x.com,70,Karachi\nnew@x.com,5,Quetta\n");
const morePath = write("more_customers.csv", "name,id,phone\nBilal,5,0300\nHina,6,0301\n");

const results = [];
async function step(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.push({ name, ok: false });
    console.log(`  ✗ ${name}\n    ${String(err.message).split("\n")[0]}`);
    throw err;
  }
}

const browser = await chromium.launch({ headless: HEADLESS });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(String(e)));
const nav = (name) => page.locator("nav[aria-label=Workspace]:visible").getByRole("button", { name }).first().click();
const preview = () => page.getByRole("button", { name: "Preview", exact: true }).click();
const apply = () => page.getByRole("button", { name: "Apply", exact: true }).click();
const shot = async (name) => SHOTS && page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
async function downloadCsv() {
  await nav("Download");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV", exact: true }).click()]);
  const file = path.join(tmp, `${Date.now()}.csv`);
  await dl.saveAs(file);
  return fs.readFileSync(file, "utf8").replace(/^﻿/, "").trimEnd().split("\n");
}

console.log(`Combine files e2e against ${BASE}`);
try {
  await step("upload the main file", async () => {
    await page.goto(BASE + "/app");
    await page.setInputFiles("input[type=file]", customersPath);
    await page.getByText("Detected issues").waitFor({ timeout: 30_000 });
  });

  await step("open Combine files and add a second file", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: /Combine files/ }).first().click();
    await page.getByText("Add the file to combine").first().waitFor().catch(() => undefined);
    assert.ok(await page.getByRole("button", { name: "Preview", exact: true }).isDisabled(), "nothing to preview before a file is added");
    await page.setInputFiles("input[aria-label='Choose the file to combine']", ordersPath);
    await page.getByText("File added").first().waitFor();
    await page.getByRole("radio", { name: /orders\.csv/ }).waitFor();
    assert.ok(await page.getByRole("radio", { name: /orders\.csv/ }).isChecked());
    await page.getByRole("table", { name: "First rows of orders.csv" }).waitFor().catch(() => page.getByText("ali@x.com").first().waitFor());
    await shot("1-file-added");
  });

  await step("join like VLOOKUP: match column suggested, preview, apply", async () => {
    await page.getByRole("radio", { name: /Add its columns to matching rows/ }).check();
    assert.equal(await page.getByLabel("Your column 1").inputValue(), "email");
    assert.equal(await page.getByLabel("Column in orders.csv 1").inputValue(), "Email");
    await preview();
    await page.getByText(/If applied: Matched 2 of 4 rows with "orders\.csv"/).waitFor();
    await page.getByText(/the first row with each value was used/).waitFor();
    await shot("2-join-preview");
    await apply();
    await page.getByText("The working data has been updated").waitFor();
  });

  await step("download contains the joined columns", async () => {
    const lines = await downloadCsv();
    assert.deepEqual(lines, [
      "id,name,email,amount,city",
      "1,Ali,ALI@x.com,100,Lahore",
      "2,Sara,sara@x.com,50,Karachi",
      "3,Omar,,,",
      "4,Zoya,zoya@x.com,,",
    ]);
  });

  await step("undo removes the joined columns", async () => {
    await page.getByRole("button", { name: "Undo last operation" }).click();
    await page.getByText("Last operation undone").waitFor();
    assert.deepEqual(await downloadCsv(), CUSTOMERS.trimEnd().split("\n"));
  });

  await step("append rows from another file with a source column", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: /Combine files/ }).first().click();
    await page.setInputFiles("input[aria-label='Choose the file to combine']", morePath);
    await page.getByRole("radio", { name: /more_customers\.csv/ }).waitFor();
    await page.getByRole("radio", { name: /Add its rows below mine/ }).check();
    await page.getByLabel("Add a column that says which file each row came from").check();
    await preview();
    await page.getByText(/If applied: Added 2 rows from "more_customers\.csv"/).waitFor();
    await page.getByText("Rows to be added").waitFor();
    await shot("3-append-preview");
    await apply();
    await page.getByText("The working data has been updated").waitFor();
    assert.deepEqual(await downloadCsv(), [
      "id,name,email,source_file,phone",
      "1,Ali,ALI@x.com,customers.csv,",
      "2,Sara,sara@x.com,customers.csv,",
      "3,Omar,,customers.csv,",
      "4,Zoya,zoya@x.com,customers.csv,",
      "5,Bilal,,more_customers.csv,0300",
      "6,Hina,,more_customers.csv,0301",
    ]);
  });

  await step("inner join asks for confirmation before removing rows", async () => {
    await nav("Clean data");
    await page.getByRole("button", { name: /Combine files/ }).first().click();
    await page.getByRole("radio", { name: /orders\.csv/ }).check();
    await page.getByRole("radio", { name: /Add its columns to matching rows/ }).check();
    await page.getByRole("radio", { name: /Only rows that match/ }).check();
    await preview();
    await page.getByText("Rows to be removed").waitFor();
    await apply();
    await page.getByRole("dialog").getByText("Remove data from the working dataset?").waitFor();
    await page.getByRole("button", { name: "Cancel" }).click();
  });

  await step("removing an added file updates the list", async () => {
    await page.getByRole("button", { name: "Remove orders.csv" }).click();
    await page.getByRole("radio", { name: /orders\.csv/ }).waitFor({ state: "detached" });
    await page.getByRole("radio", { name: /more_customers\.csv/ }).waitFor();
  });

  await step("phone width: no horizontal overflow on the Combine form", async () => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.getByRole("radio", { name: /more_customers\.csv/ }).check();
    await page.getByRole("radio", { name: /Add its columns to matching rows/ }).check();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(overflow <= 1, `page scrolls sideways by ${overflow}px`);
    await shot("4-phone");
  });

  await step("no JavaScript errors", async () => {
    assert.deepEqual(pageErrors, []);
  });
} catch {
  process.exitCode = 1;
} finally {
  await browser.close();
  const passed = results.filter((r) => r.ok).length;
  console.log(`\n${passed}/${results.length} steps passed`);
}
