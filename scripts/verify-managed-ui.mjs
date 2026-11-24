/** Real Host settings and Core authorization pages; all cookies are disposable. */
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const root = resolve(import.meta.dirname, ".."), control = process.argv[2];
const { chromium } = await import(pathToFileURL(root + "/dsh-core/web/node_modules/@playwright/test/index.mjs"));
const state = JSON.parse(await readFile(control + "/browser.json", "utf8"));
const log = await readFile(control + "/host.log", "utf8");
const hostUrl = /dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/.exec(log)?.[1];
assert.ok(hostUrl, "Host URL missing");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const errors = [], shots = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addCookies(state.cookies);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", error => errors.push(error.message));
  const consoleErrors = [];
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text().replace(/([?&]token=)[^\s&]+/g, "$1[redacted]")); });
  await page.goto(state.authorization_url);
  await page.getByRole("heading", { name: "连接 DSH 与工坊" }).waitFor();
  await page.getByRole("status").filter({ hasText: "已批准" }).waitFor();
  for (const theme of ["light", "dark"]) {
    await page.getByRole("button", { name: theme === "light" ? "浅色" : "深色", exact: true }).click();
    for (const width of [1440, 860, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      const path = control + "/authorization-" + theme + "-" + width + ".png";
      await page.screenshot({ path, fullPage: true }); shots.push(path);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "Authorization page overflow");
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(hostUrl);
  await page.waitForLoadState("networkidle");
  await writeFile(control + "/host-client-boot.json", JSON.stringify(await page.evaluate(() => window.__DSH_BOOT__), null, 2), { mode: 0o600 });
  await writeFile(control + "/host-controls.json", JSON.stringify(await page.getByRole("button").evaluateAll(nodes => nodes.map(node => ({ label: node.getAttribute("aria-label"), title: node.getAttribute("title"), text: node.textContent }))), null, 2));
  await writeFile(control + "/host-initial-text.txt", await page.locator("body").innerText(), { mode: 0o600 });
  const previewNotice = page.getByRole("button", { name: /^(继续|Continue)$/i });
  // The Host loads its first-run notice asynchronously after the app shell.
  // Each acceptance profile is fresh, so wait for that public control before
  // opening settings instead of racing the dialog's delayed mount.
  await previewNotice.waitFor({ state: "visible", timeout: 10000 }).catch(error => {
    if (error.name !== "TimeoutError") throw error;
  });
  if (await previewNotice.isVisible()) await previewNotice.click();
  await page.waitForTimeout(500);
  await page.keyboard.press("Escape");
  await writeFile(control + "/host-after-notice.txt", await page.locator("body").innerText(), { mode: 0o600 });
  await writeFile(control + "/host-console.json", JSON.stringify({ errors, consoleErrors }, null, 2));
  await page.screenshot({ path: control + "/host-after-notice.png" });
  await page.getByRole("button", { name: /账号菜单|Account menu/i }).click();
  await page.getByText(/^(Settings|设置)$/i, { exact: true }).click();
  await page.waitForTimeout(1000);
  await writeFile(control + "/host-settings-text.txt", await page.locator("body").innerText(), { mode: 0o600 });
  await writeFile(control + "/host-console.json", JSON.stringify({ errors, consoleErrors }, null, 2));
  await page.getByText("FPL 安装与连接", { exact: true }).first().click();
  await page.getByRole("heading", { name: "FPL 安装与连接" }).waitFor();
  const wizard = page.getByRole("region", { name: "FPL 安装向导" });
  await wizard.locator("[data-service]").last().waitFor();
  assert.equal(await wizard.locator("[data-service]").count(), 7);
  for (const width of [1440, 860, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const path = control + "/host-setup-" + width + ".png";
    await page.screenshot({ path, fullPage: true }); shots.push(path);
  }
  await page.getByRole("button", { name: "关闭安装设置", exact: true }).click();
  await page.getByRole("heading", { name: "FPL 安装与连接" }).waitFor({ state: "hidden" });
  await context.close();
} finally { await browser.close(); }
await writeFile(control + "/ui-report.json", JSON.stringify({ errors, screenshots: shots }, null, 2));
assert.deepEqual(errors, []);
console.log("Managed setup UI passed");
