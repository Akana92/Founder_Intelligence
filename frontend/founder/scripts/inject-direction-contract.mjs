import { access, copyFile, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const distDir = process.env.FOUNDER_NEXT_DIST_DIR?.trim() || ".next";
const layoutPath = resolve("app/layout.tsx");
const outputPath = resolve(distDir, "server/app/index.html");
const standaloneOutputPath = resolve(
  distDir,
  "standalone",
  distDir,
  "server/app/index.html",
);
const source = await readFile(layoutPath, "utf8");
const match = source.match(
  /\/\* DIRECTION_CONTRACT\s*([\s\S]*?)\s*END_DIRECTION_CONTRACT \*\//,
);

if (!match?.[1]) {
  throw new Error("Direction contract block is missing from app/layout.tsx");
}

const contract = match[1].trim();
let html = await readFile(outputPath, "utf8");

if (!html.includes("seed key 24519428")) {
  html = html.replace(/<body([^>]*)>/, `<body$1><!--\n${contract}\n-->`);
  await writeFile(outputPath, html, "utf8");
}

try {
  await access(standaloneOutputPath);
  await copyFile(outputPath, standaloneOutputPath);
  console.log(`direction contract propagated: ${standaloneOutputPath}`);
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw error;
  }
}

console.log(`direction contract injected: ${outputPath}`);
