import type {
  ScenarioKey,
  ScenarioProjectionResponse,
  StartupScenarioMetric,
} from "./contracts.ts";

export type ScenarioMetricDisclosure = Readonly<{
  metricKey: string;
  provenance: StartupScenarioMetric["provenance"];
  rangeLabel: string;
  formula: string;
  dependencies: readonly string[];
  sourceRefs: readonly string[];
  validationPlan: string;
  whatWouldConfirm: string;
  rationale: string;
  confidence: StartupScenarioMetric["confidence"];
  acceptance: StartupScenarioMetric["acceptance"];
  gaps: readonly string[];
}>;

export type ScenarioMetricComparisonValue = Readonly<{
  valueRange: StartupScenarioMetric["value_range"];
  unit: StartupScenarioMetric["unit"];
  gaps: StartupScenarioMetric["gaps"];
}>;

export type ScenarioMetricChange = Readonly<{
  metricKey: string;
  oldValue: ScenarioMetricComparisonValue;
  newValue: ScenarioMetricComparisonValue;
}>;

export type ScenarioMetricComparison = Readonly<{
  scenarioKey: ScenarioKey;
  oldRevision: number;
  newRevision: number;
  changedMetrics: readonly ScenarioMetricChange[];
}>;

export function describeScenarioMetricDisclosure(
  metric: StartupScenarioMetric,
): ScenarioMetricDisclosure {
  return {
    metricKey: metric.metric_key,
    provenance: metric.provenance,
    rangeLabel: metric.value_range
      ? `${metric.value_range.lower}-${metric.value_range.upper} ${metric.unit}`
      : "needs validation",
    formula: `${metric.formula_key}: ${metric.formula_description}`,
    dependencies: metric.dependency_refs,
    sourceRefs: metric.source_refs,
    validationPlan: metric.validation_plan,
    whatWouldConfirm: metric.what_would_confirm,
    rationale: metric.rationale,
    confidence: metric.confidence,
    acceptance: metric.acceptance,
    gaps: metric.gaps,
  };
}

function comparableMetricValue(metric: StartupScenarioMetric): ScenarioMetricComparisonValue {
  return {
    valueRange: metric.value_range,
    unit: metric.unit,
    gaps: metric.gaps,
  };
}

function missingMetricValue(
  metricKey: string,
  peerMetric: StartupScenarioMetric,
): ScenarioMetricComparisonValue {
  return {
    valueRange: null,
    unit: peerMetric.unit,
    gaps: [`missing:${metricKey}`],
  };
}

function sameRange(
  left: StartupScenarioMetric["value_range"],
  right: StartupScenarioMetric["value_range"],
): boolean {
  if (left === null || right === null) return left === right;
  return left.lower === right.lower && left.upper === right.upper;
}

function sameGaps(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function metricChanged(
  left: StartupScenarioMetric,
  right: StartupScenarioMetric,
): boolean {
  return (
    !sameRange(left.value_range, right.value_range) ||
    left.unit !== right.unit ||
    !sameGaps(left.gaps, right.gaps)
  );
}

export function compareScenarioMetricChanges(
  before: ScenarioProjectionResponse | null,
  after: ScenarioProjectionResponse,
  scenarioKey: ScenarioKey,
  oldRevision: number = before?.data_revision ?? after.data_revision,
): ScenarioMetricComparison {
  const oldMetrics = before?.scenarios[scenarioKey].metrics ?? {};
  const newMetrics = after.scenarios[scenarioKey].metrics;
  const metricKeys = [...new Set([...Object.keys(oldMetrics), ...Object.keys(newMetrics)])].sort();
  const changedMetrics = metricKeys.flatMap((metricKey) => {
    const oldMetric = oldMetrics[metricKey];
    const newMetric = newMetrics[metricKey];
    if (!oldMetric && newMetric) {
      return [{
        metricKey,
        oldValue: missingMetricValue(metricKey, newMetric),
        newValue: comparableMetricValue(newMetric),
      }];
    }
    if (oldMetric && !newMetric) {
      return [{
        metricKey,
        oldValue: comparableMetricValue(oldMetric),
        newValue: missingMetricValue(metricKey, oldMetric),
      }];
    }
    if (!oldMetric || !newMetric || !metricChanged(oldMetric, newMetric)) return [];
    return [{
      metricKey,
      oldValue: comparableMetricValue(oldMetric),
      newValue: comparableMetricValue(newMetric),
    }];
  });

  return {
    scenarioKey,
    oldRevision,
    newRevision: after.data_revision,
    changedMetrics,
  };
}
