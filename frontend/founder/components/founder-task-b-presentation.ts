export type AcceptedDocumentGateState = Readonly<{
  documentActive: boolean;
  documentCopy: string;
  documentStatus: string;
  receiptDetail: string | null;
  receiptTitle: string | null;
}>;

export function presentAcceptedDocumentGateState({
  acceptedDocumentCount,
  hasDocumentReadEvidence,
  isRunning = false,
  lastKnownStatus,
}: Readonly<{
  acceptedDocumentCount: number;
  hasDocumentReadEvidence: boolean;
  isRunning?: boolean;
  lastKnownStatus: string | null;
}>): AcceptedDocumentGateState {
  const hasAcceptedDocuments = acceptedDocumentCount > 0;
  const statusCopy = lastKnownStatus ?? "ожидаем обновление";
  const receiptTitle = hasAcceptedDocuments
    ? `Документы приняты сервером · ${acceptedDocumentCount} файл(а)`
    : null;
  const receiptDetail = hasAcceptedDocuments
    ? hasDocumentReadEvidence
      ? `Извлечение из принятого документа готово. Последний статус кейса: ${statusCopy}`
      : `Идёт обработка принятых документов. Последний статус кейса: ${statusCopy}`
    : null;

  if (hasDocumentReadEvidence) {
    return {
      documentActive: false,
      documentCopy: "Переданные материалы обработаны",
      documentStatus: "Завершено",
      receiptDetail,
      receiptTitle,
    };
  }

  if (hasAcceptedDocuments) {
    return {
      documentActive: true,
      documentCopy: "Документы приняты сервером",
      documentStatus: "В процессе",
      receiptDetail,
      receiptTitle,
    };
  }

  return {
    documentActive: isRunning,
    documentCopy: isRunning ? "Анализирует переданные материалы" : "Ожидает материалы",
    documentStatus: isRunning ? "В процессе" : "Ожидает",
    receiptDetail: null,
    receiptTitle: null,
  };
}

export type Gate2ApprovalBlock = Readonly<{
  disabledPrerequisite: string | null;
  repairCopy: string | null;
  repairLabel: string | null;
}>;

export function presentGate2ApprovalBlock({
  acceptedDocumentCount,
  canApproveGate2,
  hasDocumentReadEvidence,
}: Readonly<{
  acceptedDocumentCount: number;
  canApproveGate2: boolean;
  hasDocumentReadEvidence: boolean;
}>): Gate2ApprovalBlock {
  if (canApproveGate2 && hasDocumentReadEvidence) {
    return {
      disabledPrerequisite: null,
      repairCopy: null,
      repairLabel: null,
    };
  }

  return {
    disabledPrerequisite: acceptedDocumentCount > 0
      ? "Нужно подтверждённое извлечение из принятого документа"
      : "Нужно принять документы сервером",
    repairCopy: "Добавьте или замените документ, затем дождитесь первичного разбора.",
    repairLabel: "Исправить профиль",
  };
}

export type CaseCopilotNoActionState = Readonly<{
  recoveryDisabled: boolean;
  recoveryLabel: string;
  recoveryText: string;
  showAnswerControls: boolean;
  showPrimaryAnswerSubmit: boolean;
  showRecoveryAction: boolean;
}>;

export function presentCaseCopilotNoActionState({
  answerActionCount,
  busy,
  hasDocumentRequestHandler,
}: Readonly<{
  answerActionCount: number;
  busy: boolean;
  hasDocumentRequestHandler: boolean;
}>): CaseCopilotNoActionState {
  const hasAnswerActions = answerActionCount > 0;
  return {
    recoveryDisabled: !hasDocumentRequestHandler || busy,
    recoveryLabel: "Добавить документ",
    recoveryText: "Нужен документ или новый разбор, чтобы помощник предложил доступный ответ.",
    showAnswerControls: hasAnswerActions,
    showPrimaryAnswerSubmit: hasAnswerActions,
    showRecoveryAction: !hasAnswerActions,
  };
}
