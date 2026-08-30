import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("./upload-entry.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("./upload-entry.module.css", import.meta.url),
  "utf8",
);

function declarationBlock(selector: string): string {
  const escaped = selector.replace(".", "\\.");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`, "u"));
  assert.ok(match?.[1], `${selector} rules must exist`);
  return match[1];
}

function pxRule(block: string, property: string): number {
  const escaped = property.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const match = block.match(new RegExp(`${escaped}:\\s*(\\d+)px`, "u"));
  assert.ok(match?.[1], `${property} px rule must exist`);
  return Number.parseInt(match[1], 10);
}

test("uses scoped upload styles instead of the legacy cyan terminal classes", () => {
  assert.match(component, /import styles from "\.\/upload-entry\.module\.css"/u);
  assert.match(component, /className=\{cx\([\s\S]*styles\.entry/u);
  assert.match(component, /styles\.dropZone/u);
  assert.match(component, /styles\.primaryButton/u);
  assert.match(component, /styles\[isBusy \? "disabledButton" : "secondaryButton"\]/u);
  assert.match(component, /disabled=\{isBusy\}/u);
  assert.match(component, /Идёт обработка материалов…/u);

  assert.doesNotMatch(
    component,
    /"upload-entry|"upload-entry__|"upload-icon|"button button--primary|"button button--secondary|"text-button|"file-status|"remove-file/u,
  );
});

test("matches the approved data-room upload visual contract", () => {
  for (const selector of [
    ".entry",
    ".dropZone",
    ".uploadIcon",
    ".primaryButton",
    ".inventoryList",
    ".inventoryItem",
    ".fileTypeBadge",
    ".readyStatus",
    ".reviewStatus",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }

  assert.match(css, /\.dropZone\s*\{[\s\S]*?border:\s*1px dashed rgba\(255,\s*255,\s*255,\s*0\.26\)/u);
  assert.match(css, /\.dropZone\s*\{[\s\S]*?min-height:\s*304px[\s\S]*?padding:\s*22px/u);
  assert.match(css, /\.dashboardEntry \.dropZone\s*\{[\s\S]*?min-height:\s*340px/u);
  assert.match(css, /\.dataRoomEntry \.dropZone\s*\{[\s\S]*?min-height:\s*304px/u);
  assert.match(css, /\.uploadIcon\s*\{[\s\S]*?background:\s*rgba\(245,\s*161,\s*207,\s*0\.18\)/u);
  assert.match(css, /\.primaryButton\s*\{[\s\S]*?background:\s*linear-gradient\(135deg,\s*#f5a1cf/u);
  assert.match(css, /\.inventoryItem\s*\{[\s\S]*?border:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.13\)/u);
  assert.match(css, /\.fileTypeBadge\s*\{[\s\S]*?border-radius:\s*8px/u);
  assert.match(css, /\.readyStatus\s*\{[\s\S]*?color:\s*#86d57f/u);
  assert.match(css, /\.reviewStatus\s*\{[\s\S]*?color:\s*#f0b84c/u);
  assert.doesNotMatch(css, /--cyan|#25d7f3|#0bb6d0|font-family:\s*var\(--font-mono\)/u);
});

test("keeps the desktop upload state dense enough to fit the approved 1586x992 mockup", () => {
  const dropZone = declarationBlock(".dropZone");
  const uploadIcon = declarationBlock(".uploadIcon");
  const inventory = declarationBlock(".inventory");
  const inventoryList = declarationBlock(".inventoryList");
  const inventoryItem = declarationBlock(".inventoryItem");

  assert.equal(pxRule(dropZone, "min-height"), 304);
  assert.equal(pxRule(uploadIcon, "height"), 68);
  assert.match(css, /\.title\s*\{[\s\S]*?font-size:\s*24px/u);
  assert.match(
    css,
    /\.primaryButton,\s*\.secondaryButton,\s*\.disabledButton\s*\{[\s\S]*?min-height:\s*48px/u,
  );
  assert.ok(pxRule(inventory, "margin-top") <= 10);
  assert.ok(pxRule(inventoryList, "max-height") <= 200);
  assert.ok(pxRule(inventoryItem, "min-height") <= 56);
  assert.match(inventoryItem, /grid-template-columns:\s*42px minmax\(0,\s*1fr\) 148px 34px 24px/u);
  assert.doesNotMatch(dropZone, /display:\s*none|visibility:\s*hidden|overflow:\s*hidden/u);
  assert.doesNotMatch(inventory, /display:\s*none|visibility:\s*hidden/u);
}
);

test("keeps real upload inventory actions without fake demo files or private data", () => {
  assert.match(component, /formatFileSize\(file\.size\)/u);
  assert.match(component, /aria-label=\{`Убрать \$\{file\.name\}`\}/u);
  assert.match(component, /onClick=\{\(\) => removeFile\(file\.id\)\}/u);
  assert.match(component, /onClick=\{onStartAnalysis\}/u);
  assert.match(
    component,
    /\{onStartAnalysis \? \([\s\S]*?onClick=\{onStartAnalysis\}/u,
  );
  assert.match(component, /onInventoryChange\(\[\]\)/u);

  assert.doesNotMatch(
    component,
    /pitch_deck\.pdf|financial_model\.xlsx|customer_interviews\.csv|market_notes\.docx|sha256|[A-Z]:\\\\|\/Users\//u,
  );
});

test("uses distinct honest copy for the dashboard and the data room", () => {
  assert.match(component, /variant\?:\s*"dashboard" \| "data-room"/u);
  assert.match(component, /variant = "data-room"/u);
  assert.match(component, /variant === "dashboard"/u);
  assert.match(component, /Без выбора отрасли и без промпта/u);
  assert.match(component, /Перетащите файлы или выберите на компьютере/u);
  assert.match(component, /PDF, DOCX, XLSX, CSV, изображения и безопасный ZIP/u);
  assert.match(component, /Добавленные материалы появятся здесь/u);
  assert.doesNotMatch(component, /pitch_deck\.pdf|financial_model\.xlsx/u);
});
