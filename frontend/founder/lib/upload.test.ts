import assert from "node:assert/strict";
import test from "node:test";

import { buildLocalInventory, formatFileSize } from "./upload.ts";

test("builds a local-only inventory without file contents", () => {
  const inventory = buildLocalInventory([
    {
      name: "pitch-deck.pdf",
      size: 1_250_000,
      type: "application/pdf",
      lastModified: 1_723_456_789_000,
    },
    {
      name: "prototype.bin",
      size: 128,
      type: "application/octet-stream",
      lastModified: 1_723_456_790_000,
    },
  ]);

  assert.deepEqual(inventory[0], {
    id: "1723456789000-pitch-deck.pdf-1250000",
    name: "pitch-deck.pdf",
    size: 1_250_000,
    mimeType: "application/pdf",
    candidateStatus: "candidate",
  });
  assert.equal(inventory[1]?.candidateStatus, "review_required");
  assert.equal("content" in inventory[0]!, false);
});

test("formats file sizes for founder-readable inventory", () => {
  assert.equal(formatFileSize(0), "0 Б");
  assert.equal(formatFileSize(1_250_000), "1,25 МБ");
});
