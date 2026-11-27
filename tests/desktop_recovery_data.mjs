import { createRequire } from "node:module";
import { resolve } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
const root = resolve(import.meta.dirname, "..");
const require = createRequire(
  resolve(root, "visual-workshop/web/package.json"),
);
const { _electron, expect } = require("@playwright/test");
const titles = {
  "visual-workshop": "视觉创作工坊",
  "video-editor": "视频剪辑工坊",
  "presentation-workshop": "演示工坊",
  "thought-workshop": "思绪工坊",
  "galgame-workshop": "Galgame 工坊",
  "audio-annotation": "录音标注工坊",
};
const reports = {};
for (const repo of process.argv.slice(2)) {
  const title = titles[repo];
  if (!title) throw new Error("Unknown product");
  const output = resolve(root, ".local/desktop-recovery-real", repo);
  await mkdir(output, { recursive: true });
  const env = { ...process.env, PYTHONPATH: "" };
  delete env.FPL_DESKTOP_STATE_ROOT;
  const app = await _electron.launch({
    executablePath: resolve(
      root,
      repo,
      ".runtime/desktop/0.2.1",
      title + ".app/Contents/MacOS/Electron",
    ),
    env,
    timeout: 60000,
  });
  try {
    const page = await app.firstWindow({ timeout: 60000 });
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "项目", exact: true }).click();
    await page.waitForURL("**/apps/**");
    await expect(
      page.getByRole("button", { name: "返回首页", exact: true }),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    const endpoint =
      "/v1/" +
      repo +
      (repo === "thought-workshop" ? "/knowledge-bases" : "/projects");
    const result = await page.evaluate(async (endpoint) => {
      const response = await fetch(endpoint);
      if (!response.ok) return { status: response.status };
      const value = await response.json();
      const items = Array.isArray(value)
        ? value
        : value.items || value.projects || [];
      return {
        status: response.status,
        visible: items.length,
        total: value.total ?? items.length,
      };
    }, endpoint);
    expect(result.status).toBe(200);
    expect(result.visible).toBeGreaterThan(0);
    await page.waitForTimeout(600);
    await page.screenshot({ path: resolve(output, "projects-private.png") });
    reports[repo] = { passed: true, ...result };
    await writeFile(
      resolve(output, "result.json"),
      JSON.stringify(reports[repo], null, 2),
      { mode: 0o600 },
    );
    console.log(JSON.stringify({ product: repo, ...reports[repo] }));
  } finally {
    await app.close();
  }
}
await writeFile(
  resolve(root, ".local/desktop-recovery-real/results.json"),
  JSON.stringify(reports, null, 2),
  { mode: 0o600 },
);
