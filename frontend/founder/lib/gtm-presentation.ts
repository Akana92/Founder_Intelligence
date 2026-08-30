import type {
  StartupGtmDimensionName,
  StartupGtmDimensionStatus,
  StartupGtmExperimentCode,
  StartupGtmLaunchHorizon,
  StartupGtmResponse,
  StartupGtmStatus,
} from "./contracts.ts";

const statusLabels = {
  supported: "Подтверждено",
  partial: "Частично подтверждено",
  insufficient: "Недостаточно данных",
  contradicted: "Есть противоречия",
} satisfies Record<StartupGtmStatus, string>;

const dimensionLabels = {
  audience: "Аудитория",
  geography: "География",
  channels: "Каналы",
  offer: "Предложение",
  market_context: "Контекст рынка",
  product_proof: "Доказательства продукта",
  adoption_risk: "Риск внедрения",
} satisfies Record<StartupGtmDimensionName, string>;

const dimensionStatusLabels = {
  supported: "Подтверждено",
  partial: "Частично",
  missing: "Нет данных",
  contradicted: "Есть противоречие",
} satisfies Record<StartupGtmDimensionStatus, string>;

const horizonLabels = {
  day_7: "7 дней",
  day_30: "30 дней",
  day_60: "60 дней",
  day_90: "90 дней",
} satisfies Record<StartupGtmLaunchHorizon, string>;

const experimentLabels = {
  resolve_contradictions: "Разрешить противоречия",
  clarify_audience: "Уточнить целевую аудиторию",
  validate_geography: "Проверить географию",
  validate_channel: "Проверить канал",
  validate_offer: "Проверить предложение",
  validate_product_proof: "Проверить доказательства продукта",
  validate_market_positioning: "Проверить рыночное позиционирование",
  validate_adoption_risk: "Проверить риск внедрения",
  measure_channel_signal: "Измерить сигнал канала",
  review_launch_evidence: "Пересмотреть доказательства запуска",
} satisfies Record<StartupGtmExperimentCode, string>;

export type StartupGtmDimensionPresentation = Readonly<{
  name: StartupGtmDimensionName;
  label: string;
  status: StartupGtmDimensionStatus;
  statusLabel: string;
  evidenceFactIds: readonly string[];
  marketSourceIds: readonly string[];
  contradictionIds: readonly string[];
  reasonCode: string;
  gapCode: string | null;
}>;

export type StartupGtmLaunchStepPresentation = Readonly<{
  horizon: StartupGtmLaunchHorizon;
  label: string;
  experimentCodes: readonly StartupGtmExperimentCode[];
  experimentLabels: readonly string[];
}>;

export type StartupGtmPresentation = Readonly<{
  status: StartupGtmStatus;
  statusLabel: string;
  snapshotLabel: string;
  snapshotId: string;
  snapshotHash: string;
  findingCount: number;
  findingIds: readonly string[];
  dimensions: readonly StartupGtmDimensionPresentation[];
  launchPlan: readonly StartupGtmLaunchStepPresentation[];
  lineage: Readonly<{
    profileId: string;
    productValidationSnapshotId: string;
    marketResearchSnapshotId: string;
  }>;
}>;

export function buildStartupGtmPresentation(
  gtm: StartupGtmResponse,
): StartupGtmPresentation {
  return {
    status: gtm.status,
    statusLabel: statusLabels[gtm.status],
    snapshotLabel: `rev. ${gtm.snapshot_revision}`,
    snapshotId: gtm.snapshot_id,
    snapshotHash: gtm.snapshot_hash,
    findingCount: gtm.finding_ids.length,
    findingIds: [...gtm.finding_ids],
    dimensions: gtm.dimensions.map((dimension) => ({
      name: dimension.name,
      label: dimensionLabels[dimension.name],
      status: dimension.status,
      statusLabel: dimensionStatusLabels[dimension.status],
      evidenceFactIds: [...dimension.evidence_fact_ids],
      marketSourceIds: [...dimension.market_source_ids],
      contradictionIds: [...dimension.contradiction_ids],
      reasonCode: dimension.reason_code,
      gapCode: dimension.gap_code,
    })),
    launchPlan: gtm.launch_plan.map((step) => ({
      horizon: step.horizon,
      label: horizonLabels[step.horizon],
      experimentCodes: [...step.experiment_codes],
      experimentLabels: step.experiment_codes.map((code) => experimentLabels[code]),
    })),
    lineage: {
      profileId: gtm.profile_id,
      productValidationSnapshotId: gtm.product_validation_snapshot_id,
      marketResearchSnapshotId: gtm.market_research_snapshot_id,
    },
  };
}
