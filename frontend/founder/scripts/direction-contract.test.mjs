import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL, fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const injectScript = resolve(scriptDir, "inject-direction-contract.mjs");
const verifyScript = resolve(scriptDir, "verify-direction-contract.mjs");
let importCounter = 0;

async function runScript(scriptPath, cwd, env = {}) {
  const previousCwd = process.cwd();
  const previousEnv = new Map(
    Object.keys(env).map((key) => [key, process.env[key]]),
  );
  process.chdir(cwd);
  for (const [key, value] of Object.entries(env)) {
    process.env[key] = value;
  }
  try {
    importCounter += 1;
    await import(`${pathToFileURL(scriptPath).href}?testRun=${importCounter}`);
  } finally {
    process.chdir(previousCwd);
    for (const [key, value] of previousEnv) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }
}

async function makeBuildFixture(distDir = ".next") {
  const root = await mkdtemp(resolve(tmpdir(), "founder-direction-contract-"));
  await mkdir(resolve(root, "app"), { recursive: true });
  await mkdir(resolve(root, distDir, "server/app"), { recursive: true });
  await mkdir(resolve(root, distDir, "standalone", distDir, "server/app"), {
    recursive: true,
  });
  await writeFile(
    resolve(root, "app/layout.tsx"),
    `export default function Layout() {
  return null;
}

/* DIRECTION_CONTRACT
seed key 24519428
FINISH: update DESIGN.md before completion
END_DIRECTION_CONTRACT */
`,
    "utf8",
  );
  const html = "<html><body><main>Founder</main></body></html>";
  await writeFile(resolve(root, distDir, "server/app/index.html"), html, "utf8");
  await writeFile(
    resolve(root, distDir, "standalone", distDir, "server/app/index.html"),
    html,
    "utf8",
  );
  return root;
}

test("injects and verifies the direction contract in server and standalone root html", async () => {
  const root = await makeBuildFixture();
  try {
    await runScript(injectScript, root);

    const serverHtml = await readFile(
      resolve(root, ".next/server/app/index.html"),
      "utf8",
    );
    const standaloneHtml = await readFile(
      resolve(root, ".next/standalone/.next/server/app/index.html"),
      "utf8",
    );
    assert.match(serverHtml, /<body[^>]*>\s*<!--[\s\S]*seed key 24519428/u);
    assert.match(standaloneHtml, /<body[^>]*>\s*<!--[\s\S]*seed key 24519428/u);

    await writeFile(
      resolve(root, ".next/standalone/.next/server/app/index.html"),
      "<html><body><main>stale standalone</main></body></html>",
      "utf8",
    );
    await assert.rejects(
      runScript(verifyScript, root),
      /Built standalone root page does not preserve the direction contract/u,
    );
  } finally {
    await rm(root, { force: true, recursive: true });
  }
});

test("injects and verifies the direction contract in the configured Next distDir", async () => {
  const distDir = ".next-owner-test";
  const root = await makeBuildFixture(distDir);
  try {
    await runScript(injectScript, root, { FOUNDER_NEXT_DIST_DIR: distDir });
    await runScript(verifyScript, root, { FOUNDER_NEXT_DIST_DIR: distDir });

    const serverHtml = await readFile(
      resolve(root, distDir, "server/app/index.html"),
      "utf8",
    );
    const defaultHtmlExists = await readFile(
      resolve(root, distDir, "standalone", distDir, "server/app/index.html"),
      "utf8",
    );
    assert.match(serverHtml, /<body[^>]*>\s*<!--[\s\S]*seed key 24519428/u);
    assert.match(defaultHtmlExists, /<body[^>]*>\s*<!--[\s\S]*seed key 24519428/u);
  } finally {
    await rm(root, { force: true, recursive: true });
  }
});
