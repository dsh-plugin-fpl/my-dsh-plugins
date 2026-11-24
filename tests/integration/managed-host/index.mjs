/** Disposable Host-only control for the integration runner; never installed into a user profile. */
import { readFile, writeFile, rename } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
export const inject = ["dshCore", "tools"];
export async function* apply(ctx) {
  const base = process.env.FPL_ACCEPTANCE_CONTROL;
  if (!base) throw new Error("FPL_ACCEPTANCE_CONTROL required");
  let disposed = false, pending = Promise.resolve(), previous;
  const output = async (name, value) => {
    const path = join(base, name), tmp = path + ".tmp";
    await writeFile(tmp, JSON.stringify(value), { mode: 0o600 }); await rename(tmp, path);
  };
  const run = async () => {
    let command;
    try { command = JSON.parse(await readFile(join(base, "command.json"), "utf8")); }
    catch (error) { if (error.code === "ENOENT") return; throw error; }
    if (command.id === previous || disposed) return;
    previous = command.id;
    try {
      let value;
      if (command.kind === "invoke") {
        const result = await ctx.dshCore.invoke(command.request);
        if (!result.ok) throw Object.assign(new Error(result.error.message), { code: result.error.code });
        value = result.value;
      } else if (command.kind === "schemas") {
        value = ctx.tools.schemas().filter(row => row.name.startsWith("fpl_"));
      } else if (command.kind === "tool") {
        const signal = new AbortController();
        if (command.aborted) signal.abort();
        const result = await ctx.tools.execute({ calls: [{ type: "tool-call", id: randomUUID(), name: command.name, arguments: JSON.stringify(command.args) }], signal: signal.signal });
        value = result.results[0].result;
      } else if (command.kind === "resource") {
        value = await ctx.dshCore.importResource(Buffer.from(command.data, "base64"), command.metadata, new AbortController().signal);
      } else throw new Error("Unknown test command");
      await output("result.json", { id: command.id, ok: true, value });
    } catch (error) { await output("result.json", { id: command.id, ok: false, error: { code: error.code, message: error.message } }); }
  };
  const timer = setInterval(() => { pending = pending.then(run).catch(error => output("fixture-error.json", { message: error.message })); }, 100);
  yield async () => { disposed = true; clearInterval(timer); await pending; };
  await output("ready.json", { host: process.env.FPL_ACCEPTANCE_HOST, tools: ctx.tools.schemas().filter(row => row.name.startsWith("fpl_")).map(row => row.name) });
}
