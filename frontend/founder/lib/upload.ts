export type LocalFileLike = Readonly<{
  name: string;
  size: number;
  type: string;
  lastModified: number;
}>;

export type LocalFileInventoryItem = Readonly<{
  id: string;
  name: string;
  size: number;
  mimeType: string;
  candidateStatus: "candidate" | "review_required";
}>;

const commonDocumentCandidates = new Set([
  "csv",
  "docx",
  "jpeg",
  "jpg",
  "pdf",
  "png",
  "webp",
  "xlsx",
  "zip",
]);

function safeFileName(name: string): string {
  const leaf = name.split(/[\\/]/).at(-1) ?? "unnamed-file";
  const withoutControlCharacters = leaf.replace(/[\u0000-\u001f\u007f]/g, "");
  return withoutControlCharacters.trim() || "unnamed-file";
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLocaleLowerCase("en-US") : "";
}

export function buildLocalInventory(
  files: Iterable<LocalFileLike>,
): LocalFileInventoryItem[] {
  return Array.from(files, (file) => {
    const name = safeFileName(file.name);
    return {
      id: `${file.lastModified}-${name}-${file.size}`,
      name,
      size: file.size,
      mimeType: file.type || "application/octet-stream",
      candidateStatus: commonDocumentCandidates.has(extensionOf(name))
        ? "candidate"
        : "review_required",
    };
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1_000) {
    return `${bytes} Б`;
  }
  if (bytes < 1_000_000) {
    return `${new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 2,
    }).format(bytes / 1_000)} КБ`;
  }
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(bytes / 1_000_000)} МБ`;
}
