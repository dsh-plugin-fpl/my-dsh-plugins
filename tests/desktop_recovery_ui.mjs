import { createRequire } from "node:module";
import { resolve } from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
const repo = process.argv[2];
if (
  ![
    "visual-workshop",
    "video-editor",
    "presentation-workshop",
    "thought-workshop",
    "galgame-workshop",
    "audio-annotation",
  ].includes(repo)
)
  throw new Error("Unknown product");
const root = resolve(import.meta.dirname, ".."),
  product = resolve(root, repo);
const require = createRequire(resolve(product, "web/package.json"));
const { _electron, expect } = require("@playwright/test");
const titles = {
  "visual-workshop": "视觉创作工坊",
  "video-editor": "视频剪辑工坊",
  "presentation-workshop": "演示工坊",
  "thought-workshop": "思绪工坊",
  "galgame-workshop": "Galgame 工坊",
  "audio-annotation": "录音标注工坊",
};
const title = titles[repo],
  output = resolve(product, ".local/desktop-recovery-ui");
await mkdir(output, { recursive: true });
const app = resolve(product, ".runtime/desktop/0.2.1", title + ".app");
const build = JSON.parse(
  await readFile(
    resolve(app, "Contents/Resources/build-manifest.json"),
    "utf8",
  ),
);
expect(build.version).toBe("0.2.1");
const electron = await _electron.launch({
  executablePath: resolve(app, "Contents/MacOS/Electron"),
  timeout: 60000,
  env: {
    ...process.env,
    PYTHONPATH: "",
    FPL_DESKTOP_STATE_ROOT:
      process.env.FPL_RECOVERY_TEST_STATE_ROOT || resolve(output, "state"),
  },
});
const errors = [];
const failedAssets = [];
try {
  const page = await electron.firstWindow({ timeout: 60000 });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    if (
      (r.url().includes("/core-assets/") || r.url().includes("/providers/")) &&
      !r.ok()
    )
      failedAssets.push(r.url());
  });
  await page.waitForURL("**/core/**");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const headings = await page
    .locator(".product-home-areas h2")
    .allTextContents();
  expect(headings).toEqual(["创意", "集成", "AI 能力"]);
  expect(await page.locator(".studio-global-header").innerText()).not.toMatch(
    /设置|连接 DSH|本机所有者|登录 FPL/,
  );
  await expect(page.locator(".home-applications")).toHaveCount(0);
  await expect(page.locator(".home-hero-pet img")).toHaveJSProperty(
    "naturalWidth",
    640,
  );
  await expect(page.locator(".home-hero-pet video")).toHaveJSProperty(
    "videoWidth",
    640,
  );
  await page.getByRole("button", { name: "浅色", exact: true }).click();
  await page.screenshot({ path: resolve(output, "home-light.png") });
  await page.getByRole("button", { name: "深色", exact: true }).click();
  await page.screenshot({ path: resolve(output, "home-dark.png") });
  await page.setViewportSize({ width: 760, height: 760 });
  await page.screenshot({ path: resolve(output, "home-narrow.png") });
  await page.setViewportSize({ width: 1440, height: 960 });
  let releaseConnections;
  const connectionsReady = new Promise((resolve) => {
    releaseConnections = resolve;
  });
  await page.route(
    "**/v1/core/integrations/external-connections",
    async (route) => {
      await connectionsReady;
      await route.continue();
    },
  );
  await page.goto(
    new URL("/core/integrations?kind=external-connections", page.url()).href,
  );
  try {
    const prop = page
      .locator(".fpl-loading-scene--region .fpl-scene-prop img")
      .first();
    await expect(prop).toBeVisible();
    await expect
      .poll(() => prop.evaluate((img) => img.naturalWidth))
      .toBeGreaterThan(0);
    const runner = page.locator(
      ".fpl-loading-scene--region .fpl-scene-runner img",
    );
    await expect
      .poll(() => runner.evaluate((img) => img.naturalWidth))
      .toBeGreaterThan(0);
    await page.screenshot({ path: resolve(output, "loading.png") });
  } finally {
    releaseConnections();
  }
  await page.unrouteAll({ behavior: "wait" });
  await expect(
    page.getByRole("heading", { name: "外部连接", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "从 DSH 导入", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "导入到 DSH", exact: true }),
  ).toHaveCount(0);
  await page.locator(".connection-add-menu summary").click();
  await expect(
    page.getByRole("button", { name: "添加飞书连接", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "添加 DSH", exact: true }),
  ).toBeVisible();
  const feishu = page.locator(
    '.connection-add-menu img[src*="feishu-logo.svg"]',
  );
  await expect(feishu).toHaveJSProperty("complete", true);
  await expect
    .poll(() => feishu.evaluate((img) => img.naturalWidth))
    .toBeGreaterThan(0);
  await page.screenshot({ path: resolve(output, "connection-menu.png") });
  await page.getByRole("button", { name: "添加飞书连接", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "添加飞书连接", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.locator(".connection-add-menu summary").click();
  await page.getByRole("button", { name: "添加 DSH", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "连接 DSH", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.goto(new URL("/core/code-agents", page.url()).href);
  const pi = page.locator('img[src*="pi-logo.svg"]').first();
  await expect(pi).toHaveJSProperty("complete", true);
  await expect
    .poll(() => pi.evaluate((img) => img.naturalWidth))
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "项目", exact: true }).click();
  await page.waitForURL("**/apps/**");
  await expect(
    page.getByRole("button", { name: "返回首页", exact: true }),
  ).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect
    .poll(() =>
      page.locator(".workshop-brand img").evaluate((img) => img.naturalWidth),
    )
    .toBeGreaterThan(0);
  const nativeAssets = await page.evaluate(async (repo) => {
    const image = document.querySelector(".workshop-brand img");
    const [mark, icon, thumbnail, loader] = await Promise.all([
      fetch(`/brand/${repo}-mark.png`),
      fetch("/app-icon.svg"),
      fetch(image.currentSrc),
      fetch("/brand/loading/kurisu-run.webp"),
    ]);
    const first = new Uint8Array(await mark.arrayBuffer());
    const second = new Uint8Array(await icon.arrayBuffer());
    return {
      sameMark:
        first.length === second.length &&
        first.every((value, index) => value === second[index]),
      types: [
        thumbnail.headers.get("content-type"),
        loader.headers.get("content-type"),
      ],
      thumbnail:
        thumbnail.ok &&
        thumbnail.headers.get("content-type")?.includes("image/webp"),
      loading:
        loader.ok && loader.headers.get("content-type")?.includes("image/webp"),
    };
  }, repo);
  expect(nativeAssets).toMatchObject({
    sameMark: true,
    thumbnail: true,
    loading: true,
  });
  if (repo === "presentation-workshop")
    await expect(page.locator(".presentation-create-card")).toHaveCount(0);
  await page.screenshot({ path: resolve(output, "projects.png") });
  const menu = await electron.evaluate(({ Menu }) =>
    Menu.getApplicationMenu().items.flatMap(
      (x) => x.submenu?.items.map((y) => y.label) || [],
    ),
  );
  expect(menu).toEqual(expect.arrayContaining(["设置…", "账号", "旧文件整理"]));
  if (errors.length || failedAssets.length)
    throw new Error(JSON.stringify({ errors, failedAssets }));
  await writeFile(
    resolve(output, "result.json"),
    JSON.stringify(
      {
        passed: true,
        product: repo,
        build,
        areas: headings,
        originalCharacter: true,
        nativeAssets,
        menu: true,
        errors,
        failedAssets,
      },
      null,
      2,
    ),
  );
  console.log("UI acceptance passed:", repo);
} finally {
  await electron.close();
}
