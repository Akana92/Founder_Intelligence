type FounderWorkspaceAnalysisStartInstance = Readonly<{
  start: (files: readonly File[]) => Promise<boolean>;
  getSnapshot: () => Readonly<{ uploadAccepted: boolean }>;
}>;

export async function startFounderWorkspaceAnalysis({
  clearDraft,
  getCurrentInstance,
  selectedFiles,
}: Readonly<{
  clearDraft: (acceptedFiles: readonly File[]) => void;
  getCurrentInstance: () => FounderWorkspaceAnalysisStartInstance | null;
  selectedFiles: readonly File[];
}>): Promise<boolean> {
  const instance = getCurrentInstance();
  if (!instance) return false;
  const acceptedByThisStart = await instance.start(selectedFiles);
  if (getCurrentInstance() !== instance) return false;
  if (acceptedByThisStart && instance.getSnapshot().uploadAccepted === true) {
    clearDraft(selectedFiles);
    return true;
  }
  return false;
}
