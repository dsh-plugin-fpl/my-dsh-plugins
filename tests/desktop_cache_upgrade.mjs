import { createRequire } from "node:module";
import { resolve } from "node:path";
import { readdir, mkdir, mkdtemp, writeFile } from "node:fs/promises";
const root = resolve(import.meta.dirname, ".."),
  product = resolve(root, "audio-annotation");
const require = createRequire(resolve(product, "web/package.json"));
const { _electron, expect } = require("@playwright/test");
const output = resolve(product, ".local/desktop-cache-upgrade");
await mkdir(output, { recursive: true });
const state = await mkdtemp(resolve(output, "state-"));
const stages = await readdir(resolve(product, ".runtime/desktop"));
const old = stages
  .filter((x) => x.startsWith("0.2.1-before-native-assets-"))
  .sort()
  .at(-1);
if (!old)
  throw new Error(
    "Preserved pre-fix candidate is required for cache upgrade acceptance",
  );
const launch = (stage) =>
  _electron.launch({
    executablePath: resolve(
      product,
      ".runtime/desktop",
      stage,
      "录音标注工坊.app/Contents/MacOS/Electron",
    ),
    env: { ...process.env, PYTHONPATH: "", FPL_DESKTOP_STATE_ROOT: state },
    timeout: 60000,
  });
let app = await launch(old);
let identity;
try {
  const page = await app.firstWindow();
  await expect(
    page.getByRole("heading", { name: "录音标注工坊", exact: true }),
  ).toBeVisible();
  identity = await page.evaluate(async () => {
    localStorage.setItem("fpl-cache-upgrade-proof", "preserved");
    const legacy = await fetch("/brand/loading/kurisu-run.webp");
    if (!legacy.headers.get("content-type")?.includes("svg"))
      throw new Error("Legacy placeholder cache was not reproduced");
    return (await fetch("/v1/auth/me").then((r) => r.json())).user.id;
  });
} finally {
  await app.close();
}
app = await launch("0.2.1");
let result;
try {
  const page = await app.firstWindow();
  await expect(
    page.getByRole("heading", { name: "录音标注工坊", exact: true }),
  ).toBeVisible();
  result = await page.evaluate(async (identity) => {
    const response = await fetch("/brand/loading/kurisu-run.webp");
    const current = await fetch("/v1/auth/me").then((r) => r.json());
    return {
      httpCacheRefreshed: response.headers
        .get("content-type")
        ?.includes("image/webp"),
      localStoragePreserved:
        localStorage.getItem("fpl-cache-upgrade-proof") === "preserved",
      identityPreserved: current.user.id === identity,
    };
  }, identity);
  expect(result).toEqual({
    httpCacheRefreshed: true,
    localStoragePreserved: true,
    identityPreserved: true,
  });
} finally {
  await app.close();
}
await writeFile(
  resolve(output, "result.json"),
  JSON.stringify(result, null, 2),
);
console.log("HTTP cache refreshed; local storage and account preserved");
