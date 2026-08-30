import assert from "node:assert/strict";
import test from "node:test";

import {
  clearStoredFounderCaseId,
  FOUNDER_ACTIVE_CASE_STORAGE_KEY,
  readStoredFounderCaseId,
  writeStoredFounderCaseId,
} from "./founder-case-storage.ts";

class MemoryStorage implements Storage {
  private readonly entries = new Map<string, string>();

  get length(): number {
    return this.entries.size;
  }

  clear(): void {
    this.entries.clear();
  }

  getItem(key: string): string | null {
    return this.entries.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.entries.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.entries.delete(key);
  }

  setItem(key: string, value: string): void {
    this.entries.set(key, value);
  }
}

test("stores only the active case UUID under a versioned key", () => {
  const storage = new MemoryStorage();
  const caseId = "11111111-1111-4111-8111-111111111111";

  writeStoredFounderCaseId(storage, caseId);

  assert.equal(FOUNDER_ACTIVE_CASE_STORAGE_KEY, "founder.activeCaseId.v1");
  assert.equal(storage.length, 1);
  assert.equal(storage.getItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY), caseId);
  assert.equal(readStoredFounderCaseId(storage), caseId);
  assert.doesNotMatch(storage.getItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY) ?? "", /Smart|University|pdf|document|research|source|FounderCo/iu);
});

test("removes invalid stored case IDs instead of returning them", () => {
  const storage = new MemoryStorage();
  storage.setItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY, JSON.stringify({
    caseId: "11111111-1111-4111-8111-111111111111",
    document: "private plan text",
  }));

  assert.equal(readStoredFounderCaseId(storage), null);
  assert.equal(storage.getItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY), null);
});

test("clears stale stored case IDs explicitly", () => {
  const storage = new MemoryStorage();
  writeStoredFounderCaseId(storage, "11111111-1111-4111-8111-111111111111");

  clearStoredFounderCaseId(storage);

  assert.equal(storage.getItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY), null);
});
