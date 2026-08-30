import assert from "node:assert/strict";
import test from "node:test";

import {
  compareScenarioMetricChanges,
  describeScenarioMetricDisclosure,
} from "./scenario-presentation.ts";
import type { ScenarioProjectionResponse, StartupScenarioMetric } from "./contracts.ts";

const metric: StartupScenarioMetric = {
  metric_id: "44444444-4444-4444-8444-444444444444",
  case_id: "11111111-1111-4111-8111-111111111111",
  data_revision: 3,
  metric_key: "mrr",
  value_range: { lower: "1400000", upper: "2000000" },
  unit: "KZT/month",
  period: "month",
  provenance: "deterministic_calculation",
  source_refs: [],
  dependency_refs: [
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
  ],
  formula_key: "mrr",
  formula_description: "monthly_price * paying_customers",
  confidence: "medium",
  rationale: "Derived from scenario inputs.",
  validation_plan: "Validate against billing export.",
  what_would_confirm: "Billing export with paid customer count.",
  acceptance: "needs_validation",
  gaps: [],
};

test("scenario metric disclosure exposes provenance, range, formula, dependencies and validation plan", () => {
  const disclosure = describeScenarioMetricDisclosure(metric);

  assert.equal(disclosure.metricKey, "mrr");
  assert.equal(disclosure.provenance, "deterministic_calculation");
  assert.equal(disclosure.rangeLabel, "1400000-2000000 KZT/month");
  assert.equal(disclosure.formula, "mrr: monthly_price * paying_customers");
  assert.deepEqual(disclosure.dependencies, metric.dependency_refs);
  assert.equal(disclosure.validationPlan, "Validate against billing export.");
  assert.equal(disclosure.whatWouldConfirm, "Billing export with paid customer count.");
  assert.equal(disclosure.sourceRefs.length, 0);
});

test("scenario metric disclosure never renders a missing actual as zero", () => {
  const disclosure = describeScenarioMetricDisclosure({
    ...metric,
    value_range: null,
    gaps: ["missing_churn"],
  });

  assert.equal(disclosure.rangeLabel, "needs validation");
  assert.doesNotMatch(JSON.stringify(disclosure), /(^|[^0-9])0([^0-9]|$)/u);
  assert.deepEqual(disclosure.gaps, ["missing_churn"]);
});

function scenarioProjection(
  revision: number,
  metricOverrides: Partial<StartupScenarioMetric> = {},
  metricKeys: readonly string[] = ["mrr", "cac"],
): ScenarioProjectionResponse {
  const scenarioMetric: StartupScenarioMetric = {
    ...metric,
    data_revision: revision,
    value_range: { lower: "1400000", upper: "2000000" },
    unit: "KZT/month",
    gaps: [],
    ...metricOverrides,
  };
  const metrics: Record<string, StartupScenarioMetric> = {};
  if (metricKeys.includes("mrr")) metrics.mrr = scenarioMetric;
  if (metricKeys.includes("cac")) {
    metrics.cac = {
      ...metric,
      data_revision: revision,
      metric_id: "99999999-9999-4999-8999-999999999999",
      metric_key: "cac",
      value_range: { lower: "25000", upper: "35000" },
      unit: "KZT",
      formula_key: "cac",
      gaps: [],
    };
  }
  const variant = (scenarioKey: "conservative" | "base" | "optimistic") => ({
    scenario_key: scenarioKey,
    inputs: {},
    metrics,
    gaps: {},
  });
  return {
    scenario_set_id: "88888888-8888-4888-8888-888888888888",
    case_id: "11111111-1111-4111-8111-111111111111",
    data_revision: revision,
    selected_scenario_key: "base",
    scenarios: {
      conservative: variant("conservative"),
      base: variant("base"),
      optimistic: variant("optimistic"),
    },
    fact_coverage: {
      measure: "fact_coverage",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
    scenario_completeness: {
      measure: "scenario_completeness",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
  };
}

test("compares same-scenario metrics across revisions without reporting unchanged metrics", () => {
  const comparison = compareScenarioMetricChanges(
    scenarioProjection(4),
    scenarioProjection(5, { value_range: { lower: "1800000", upper: "2600000" } }),
    "base",
  );

  assert.deepEqual(comparison, {
    scenarioKey: "base",
    oldRevision: 4,
    newRevision: 5,
    changedMetrics: [
      {
        metricKey: "mrr",
        oldValue: {
          valueRange: { lower: "1400000", upper: "2000000" },
          unit: "KZT/month",
          gaps: [],
        },
        newValue: {
          valueRange: { lower: "1800000", upper: "2600000" },
          unit: "KZT/month",
          gaps: [],
        },
      },
    ],
  });
});

test("compares newly calculable metrics with a missing side instead of invented zero", () => {
  const comparison = compareScenarioMetricChanges(
    scenarioProjection(4, { value_range: null, gaps: ["missing:monthly_price"] }),
    scenarioProjection(5, { value_range: { lower: "1800000", upper: "2600000" }, gaps: [] }),
    "base",
  );

  assert.deepEqual(comparison.changedMetrics[0], {
    metricKey: "mrr",
    oldValue: {
      valueRange: null,
      unit: "KZT/month",
      gaps: ["missing:monthly_price"],
    },
    newValue: {
      valueRange: { lower: "1800000", upper: "2600000" },
      unit: "KZT/month",
      gaps: [],
    },
  });
  assert.doesNotMatch(JSON.stringify(comparison.changedMetrics[0]?.oldValue), /"0"/u);
});

test("compares metrics that appear after research without dropping absent old keys", () => {
  const comparison = compareScenarioMetricChanges(
    scenarioProjection(4, {}, ["cac"]),
    scenarioProjection(5, { value_range: { lower: "1800000", upper: "2600000" } }, ["mrr", "cac"]),
    "base",
  );

  assert.deepEqual(comparison.changedMetrics[0], {
    metricKey: "mrr",
    oldValue: {
      valueRange: null,
      unit: "KZT/month",
      gaps: ["missing:mrr"],
    },
    newValue: {
      valueRange: { lower: "1800000", upper: "2600000" },
      unit: "KZT/month",
      gaps: [],
    },
  });
  assert.doesNotMatch(JSON.stringify(comparison.changedMetrics[0]?.oldValue), /"0"/u);
});

test("compares metrics removed after recalculation with a missing new side", () => {
  const comparison = compareScenarioMetricChanges(
    scenarioProjection(4, { value_range: { lower: "1400000", upper: "2000000" } }, ["mrr", "cac"]),
    scenarioProjection(5, {}, ["cac"]),
    "base",
  );

  assert.deepEqual(comparison.changedMetrics[0], {
    metricKey: "mrr",
    oldValue: {
      valueRange: { lower: "1400000", upper: "2000000" },
      unit: "KZT/month",
      gaps: [],
    },
    newValue: {
      valueRange: null,
      unit: "KZT/month",
      gaps: ["missing:mrr"],
    },
  });
  assert.doesNotMatch(JSON.stringify(comparison.changedMetrics[0]?.newValue), /"0"/u);
});

test("compares after metrics against an unavailable before projection without inventing zero", () => {
  const comparison = compareScenarioMetricChanges(
    null,
    scenarioProjection(5, { value_range: { lower: "1800000", upper: "2600000" } }, ["mrr", "cac"]),
    "base",
    4,
  );

  assert.deepEqual(comparison, {
    scenarioKey: "base",
    oldRevision: 4,
    newRevision: 5,
    changedMetrics: [
      {
        metricKey: "cac",
        oldValue: {
          valueRange: null,
          unit: "KZT",
          gaps: ["missing:cac"],
        },
        newValue: {
          valueRange: { lower: "25000", upper: "35000" },
          unit: "KZT",
          gaps: [],
        },
      },
      {
        metricKey: "mrr",
        oldValue: {
          valueRange: null,
          unit: "KZT/month",
          gaps: ["missing:mrr"],
        },
        newValue: {
          valueRange: { lower: "1800000", upper: "2600000" },
          unit: "KZT/month",
          gaps: [],
        },
      },
    ],
  });
  assert.doesNotMatch(JSON.stringify(comparison.changedMetrics), /"0"/u);
});
