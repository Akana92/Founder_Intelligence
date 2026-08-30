import { access, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const distDir = process.env.FOUNDER_NEXT_DIST_DIR?.trim() || ".next";
const outputPath = resolve(distDir, "server/app/index.html");
const standaloneOutputPath = resolve(
  distDir,
  "standalone",
  distDir,
  "server/app/index.html",
);

async function verifyOutput(path, label) {
  const html = await readFile(path, "utf8");
  const firstBodyChildIsContract =
    /<body[^>]*>\s*<!--[\s\S]*?seed key 24519428[\s\S]*?FINISH:[\s\S]*?DESIGN\.md[\s\S]*?-->/.test(
      html,
    );
  if (!firstBodyChildIsContract) {
    throw new Error(
      `Built ${label} root page does not preserve the direction contract as the first body child`,
    );
  }
  console.log(`direction contract verified: ${path}`);
}

await verifyOutput(outputPath, "server");

try {
  await access(standaloneOutputPath);
  await verifyOutput(standaloneOutputPath, "standalone");
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw error;
  }
}
