import {
  capabilityByKey,
  capabilityKeys,
  type CapabilityKey,
  type LifecycleStatus,
  type ProductCapabilities,
} from "./contracts.ts";

export type CapabilityBoundaryLoadState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "ready"; contract: ProductCapabilities }>
  | Readonly<{ kind: "unavailable" }>;

type PresentedCapability = Readonly<{
    key: CapabilityKey;
    label: string;
    lifecycle: LifecycleStatus;
    lifecycleLabel: string;
}>;

export type CapabilityBoundaryPresentation =
  | Readonly<{
      kind: "loading";
      title: string;
      detail: null;
      capabilities: readonly [];
    }>
  | Readonly<{
      kind: "unavailable";
      title: string;
      detail: string;
      capabilities: readonly [];
    }>
  | Readonly<{
      kind: "ready";
      title: string;
      detail: string;
      capabilities: readonly PresentedCapability[];
    }>;

const labels: Record<CapabilityKey, string> = {
  universal_upload: "Безопасная загрузка материалов",
  primary_startup_analysis: "Первичный анализ",
  deep_startup_analysis: "Глубинный анализ",
  public_comparable_analysis: "Публичные аналоги",
};

const lifecycleCopy: Record<LifecycleStatus, string> = {
  available: "Доступно",
  planned: "Следующая стадия",
  unavailable: "Недоступно",
};

export const founderDocumentTransitCopy =
  "До запуска выбранные файлы остаются локально. После подтверждения запуска они отправляются в приватный рабочий кейс через безопасную загрузку; неподтверждённые результаты не подставляются.";

export function presentCapabilityBoundary(
  state: CapabilityBoundaryLoadState,
): CapabilityBoundaryPresentation {
  if (state.kind === "loading") {
    return {
      kind: "loading",
      title: "Проверяем доступность сервиса анализа…",
      detail: null,
      capabilities: [],
    };
  }

  if (state.kind === "unavailable") {
    return {
      kind: "unavailable",
      title: "Сервис анализа недоступен",
      detail:
        "Загрузка и анализ не запускаются до восстановления сервиса. Результаты не имитируются и тестовый режим не включается автоматически.",
      capabilities: [],
    };
  }

  const capabilities = capabilityKeys.map((key) => {
    const capability = capabilityByKey(state.contract, key);
    return {
      key,
      label: labels[key],
      lifecycle: capability.lifecycle_status,
      lifecycleLabel: lifecycleCopy[capability.lifecycle_status],
    };
  });
  const liveStartupPath = capabilities
    .filter(
      (item) =>
        item.key === "universal_upload" ||
        item.key === "primary_startup_analysis",
    )
    .every((item) => item.lifecycle === "available");

  return {
    kind: "ready",
    title: liveStartupPath ? "Рабочая система анализа подключена" : "Возможности сервиса подтверждены",
    detail: liveStartupPath
      ? "После запуска документы передаются в приватный рабочий кейс. Доступность глубокого анализа и публичных аналогов показана отдельно ниже."
      : "Доступность загрузки и анализа определяется текущими возможностями сервиса; недоступные этапы не подменяются тестовыми результатами.",
    capabilities,
  };
}
