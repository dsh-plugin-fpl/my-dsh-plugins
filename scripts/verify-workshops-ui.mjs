import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
const base = process.env.WORKSHOPS_WORKSPACE,
  task = process.env.WORKSHOPS_TEST_ROOT;
const { chromium } = await import(
  pathToFileURL(
    base + "/dsh-visual-workshop/web/node_modules/@playwright/test/index.mjs",
  ).href
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const result = [];
try {
  for (const [slug, route, port, button] of [
    ["dsh-visual-workshop", "visual-workshop", 19360, "新建项目"],
    ["dsh-video-editor", "video-editor", 19361, "新建剪辑"],
  ]) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 960 },
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [],
      failed = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("response", (r) => {
      if (r.status() >= 400 && r.url().startsWith("http://127.0.0.1:" + port))
        failed.push({ status: r.status(), url: r.url() });
    });
    const link = JSON.parse(
      await readFile(task + "/" + slug + "-browser.json", "utf8"),
    );
    await page.goto(link.url);
    await page
      .getByRole("button", { name: button, exact: true })
      .first()
      .waitFor();
    await page.screenshot({
      path: task + "/" + slug + "-projects-light.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "深色", exact: true })
      .first()
      .click();
    await page.screenshot({
      path: task + "/" + slug + "-projects-dark.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "浅色", exact: true })
      .first()
      .click();
    await page
      .getByRole("button", { name: button, exact: true })
      .first()
      .click();
    await page.waitForURL(/projects\//);
    await page.waitForTimeout(1800);
    await page.screenshot({
      path: task + "/" + slug + "-editor-wide.png",
      fullPage: true,
    });
    const editorTheme = page.getByRole("button", {
      name: "切换深色",
      exact: true,
    });
    if (await editorTheme.count()) await editorTheme.click();
    else if (
      await page.getByRole("button", { name: "深色", exact: true }).count()
    )
      await page
        .getByRole("button", { name: "深色", exact: true })
        .first()
        .click();
    await page.screenshot({
      path: task + "/" + slug + "-editor-dark.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 768, height: 900 });
    await page.screenshot({
      path: task + "/" + slug + "-editor-narrow.png",
      fullPage: true,
    });
    result.push({ slug, errors, failed, created_project: true });
    await context.close();
  }
} finally {
  await browser.close();
}
await writeFile(task + "/ui-result.json", JSON.stringify(result, null, 2));
if (result.some((r) => r.errors.length || r.failed.length))
  throw new Error(JSON.stringify(result));
console.log("WORKSHOP_UI_PASSED");
