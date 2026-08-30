import assert from "node:assert/strict";
import test from "node:test";

import type { StartupGtmResponse } from "./contracts.ts";
import { buildStartupGtmPresentation } from "./gtm-presentation.ts";

const startupGtm: StartupGtmResponse = {
  case_id: "case-founder-001",
  schema_version: "startup_gtm@1",
  snapshot_id: "gtm-snapshot-004",
  snapshot_hash:
    "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  snapshot_revision: 4,
  status: "partial",
  profile_id: "profile-founder-001",
  product_validation_snapshot_id: "product-validation-snapshot-001",
  market_research_snapshot_id: "market-research-snapshot-001",
  dimensions: [
    {
      name: "audience",
      status: "supported",
      evidence_fact_ids: ["fact-audience-001"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_audience_supported",
      gap_code: null,
    },
    {
      name: "geography",
      status: "partial",
      evidence_fact_ids: ["fact-geography-001"],
      market_source_ids: ["market-source-geography-001"],
      contradiction_ids: [],
      reason_code: "gtm_geography_partial",
      gap_code: "gtm_geography_gap",
    },
    {
      name: "channels",
      status: "missing",
      evidence_fact_ids: [],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_channels_missing",
      gap_code: "gtm_channels_gap",
    },
    {
      name: "offer",
      status: "supported",
      evidence_fact_ids: ["fact-offer-001"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_offer_supported",
      gap_code: null,
    },
    {
      name: "market_context",
      status: "supported",
      evidence_fact_ids: [],
      market_source_ids: ["market-source-context-001"],
      contradiction_ids: [],
      reason_code: "gtm_market_context_supported",
      gap_code: null,
    },
    {
      name: "product_proof",
      status: "contradicted",
      evidence_fact_ids: ["fact-product-proof-001"],
      market_source_ids: [],
      contradiction_ids: ["contradiction-product-proof-001"],
      reason_code: "gtm_product_proof_contradicted",
      gap_code: "gtm_product_proof_gap",
    },
    {
      name: "adoption_risk",
      status: "partial",
      evidence_fact_ids: ["fact-adoption-risk-001"],
      market_source_ids: ["market-source-risk-001"],
      contradiction_ids: [],
      reason_code: "gtm_adoption_risk_partial",
      gap_code: "gtm_adoption_risk_gap",
    },
  ],
  launch_plan: [
    {
      horizon: "day_7",
      experiment_codes: ["clarify_audience", "resolve_contradictions"],
    },
    {
      horizon: "day_30",
      experiment_codes: ["validate_geography", "validate_channel"],
    },
    {
      horizon: "day_60",
      experiment_codes: ["validate_offer", "validate_product_proof"],
    },
    {
      horizon: "day_90",
      experiment_codes: ["measure_channel_signal", "review_launch_evidence"],
    },
  ],
  finding_ids: ["gtm-finding-001", "gtm-finding-002"],
  built_at: "2026-08-15T00:00:00.000Z",
};

test("projects all frozen GTM dimensions without inventing scores", () => {
  const presentation = buildStartupGtmPresentation(startupGtm);

  assert.equal(presentation.statusLabel, "Частично подтверждено");
  assert.equal(presentation.snapshotLabel, "rev. 4");
  assert.equal(presentation.findingCount, 2);
  assert.deepEqual(
    presentation.dimensions.map((dimension) => [
      dimension.name,
      dimension.label,
      dimension.statusLabel,
    ]),
    [
      ["audience", "Аудитория", "Подтверждено"],
      ["geography", "География", "Частично"],
      ["channels", "Каналы", "Нет данных"],
      ["offer", "Предложение", "Подтверждено"],
      ["market_context", "Контекст рынка", "Подтверждено"],
      ["product_proof", "Доказательства продукта", "Есть противоречие"],
      ["adoption_risk", "Риск внедрения", "Частично"],
    ],
  );
  assert.deepEqual(presentation.dimensions[5]?.evidenceFactIds, [
    "fact-product-proof-001",
  ]);
  assert.deepEqual(presentation.dimensions[5]?.contradictionIds, [
    "contradiction-product-proof-001",
  ]);
  assert.equal(presentation.dimensions[5]?.gapCode, "gtm_product_proof_gap");
  assert.equal("score" in presentation.dimensions[5]!, false);
});

test("projects the frozen 7/30/60/90 launch plan and preserves experiment codes", () => {
  const presentation = buildStartupGtmPresentation(startupGtm);

  assert.deepEqual(
    presentation.launchPlan.map((step) => [step.horizon, step.label]),
    [
      ["day_7", "7 дней"],
      ["day_30", "30 дней"],
      ["day_60", "60 дней"],
      ["day_90", "90 дней"],
    ],
  );
  assert.deepEqual(presentation.launchPlan[0]?.experimentCodes, [
    "clarify_audience",
    "resolve_contradictions",
  ]);
  assert.deepEqual(presentation.launchPlan[0]?.experimentLabels, [
    "Уточнить целевую аудиторию",
    "Разрешить противоречия",
  ]);
  assert.deepEqual(presentation.lineage, {
    profileId: "profile-founder-001",
    productValidationSnapshotId: "product-validation-snapshot-001",
    marketResearchSnapshotId: "market-research-snapshot-001",
  });
});
