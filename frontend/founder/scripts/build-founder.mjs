import { spawn } from "node:child_process";
import { lstat, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import process from "node:process";

async function isLinkedNodeModules() {
  try {
    return (await lstat(resolve("node_modules"))).isSymbolicLink();
  } catch {
    return false;
  }
}

function runNodeScript(args, env) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, args, {
      env,
      stdio: "inherit",
      windowsHide: true,
    });
    child.on("error", rejectRun);
    child.on("exit", (code, signal) => {
      if (code === 0) {
        resolveRun();
        return;
      }
      rejectRun(
        new Error(
          signal
            ? `${args.join(" ")} failed with signal ${signal}`
            : `${args.join(" ")} failed with exit code ${code}`,
        ),
      );
    });
  });
}

const env = { ...process.env };
const tsconfigPath = resolve("tsconfig.json");
const tsconfigBeforeBuild = await readFile(tsconfigPath, "utf8");

if (process.platform === "win32" && (await isLinkedNodeModules())) {
  env.FOUNDER_NEXT_STANDALONE ??= "0";
  if (env.FOUNDER_NEXT_STANDALONE === "0") {
    console.log(
      "standalone output disabled for Windows linked node_modules build; packaged builds keep standalone with local node_modules",
    );
  }
}

try {
  await runNodeScript(["node_modules/next/dist/bin/next", "build", "--webpack"], env);
} finally {
  await writeFile(tsconfigPath, tsconfigBeforeBuild, "utf8");
}
await runNodeScript(["scripts/inject-direction-contract.mjs"], env);
await runNodeScript(["scripts/verify-direction-contract.mjs"], env);
