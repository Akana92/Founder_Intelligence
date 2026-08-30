export const FOUNDER_ACTIVE_CASE_STORAGE_KEY = "founder.activeCaseId.v1";

const FOUNDER_CASE_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export function isFounderCaseId(value: string): boolean {
  return FOUNDER_CASE_ID_PATTERN.test(value.trim());
}

export function readStoredFounderCaseId(storage: Storage): string | null {
  let value: string | null = null;
  try {
    value = storage.getItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (isFounderCaseId(normalized)) return normalized;
  clearStoredFounderCaseId(storage);
  return null;
}

export function writeStoredFounderCaseId(storage: Storage, caseId: string): void {
  const normalized = caseId.trim().toLowerCase();
  if (!isFounderCaseId(normalized)) return;
  try {
    storage.setItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY, normalized);
  } catch {
    // Storage can be unavailable in restricted browser modes; resume is optional.
  }
}

export function clearStoredFounderCaseId(storage: Storage): void {
  try {
    storage.removeItem(FOUNDER_ACTIVE_CASE_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser modes; clearing is best effort.
  }
}
