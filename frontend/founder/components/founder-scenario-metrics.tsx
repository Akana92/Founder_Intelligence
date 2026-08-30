"use client";

import { ChevronDown } from "lucide-react";

import type {
  CopilotCoverageProjection,
  ScenarioKey,
  ScenarioProjectionResponse,
  StartupScenarioVariant,
} from "@/lib/contracts";
import {
  formatCoverage,
  formatScenario,
  presentScenarioMetric,
} from "@/lib/founder-readable-presentation";

import styles from "./case-copilot-panel.module.css";

export type FounderScenarioMetricsProps = Readonly<{
  busy?: boolean;
  factCoverage: CopilotCoverageProjection | null;
  scenarioCompleteness: CopilotCoverageProjection | null;
  scenarios: ScenarioProjectionResponse | null;
  selectedScenario: StartupScenarioVariant | null;
  onScenarioSelect?: (scenarioKey: ScenarioKey) => Promise<boolean> | boolean;
}>;

export function FounderScenarioMetrics({
  busy = false,
  factCoverage,
  onScenarioSelect,
  scenarioCompleteness,
  scenarios,
  selectedScenario,
}: FounderScenarioMetricsProps) {
  const metrics = selectedScenario ? Object.values(selectedScenario.metrics) : [];

  return (
    <section className={styles.scenarioMetrics} data-founder-scenario-metrics>
      <div className={styles.coverageSplit}>
        <span><strong>Покрытие фактами</strong>{formatCoverage(factCoverage)}</span>
        <span><strong>Полнота сценария</strong>{formatCoverage(scenarioCompleteness)}</span>
      </div>

      {scenarios ? (
        <div className={styles.scenarioSelector} role="group" aria-label="Выбор сценария">
          {(["conservative", "base", "optimistic"] as const).map((scenarioKey) => (
            <button
              aria-pressed={scenarios.selected_scenario_key === scenarioKey}
              disabled={busy || !onScenarioSelect}
              key={scenarioKey}
              onClick={() => void onScenarioSelect?.(scenarioKey)}
              type="button"
            >
              {formatScenario(scenarioKey)}
            </button>
          ))}
        </div>
      ) : (
        <p className={styles.blocker}>Сценарные расчёты ещё не готовы.</p>
      )}

      <div className={styles.metricList}>
        {metrics.length > 0 ? metrics.map((metric) => {
          const presentation = presentScenarioMetric(metric);
          return (
            <article className={styles.metricDisclosure} key={metric.metric_id}>
              <div>
                <span>
                  <strong>{presentation.title}</strong>
                  <em data-provenance={metric.provenance}>{presentation.trustStatement}</em>
                </span>
                <span>{presentation.value}</span>
              </div>
              <details>
                <summary>Как рассчитано и проверить</summary>
                <ChevronDown aria-hidden="true" size={16} />
                <dl>
                  <div><dt>Происхождение</dt><dd>{presentation.trustStatement}</dd></div>
                  <div><dt>Диапазон</dt><dd>{presentation.value}</dd></div>
                  <div><dt>Формула</dt><dd>{presentation.formula}</dd></div>
                  <div>
                    <dt>Зависимости</dt>
                    <dd>{presentation.dependencies.length > 0
                      ? presentation.dependencies.map((dependency, index) => <span key={`${dependency}-${index}`}>{dependency}</span>)
                      : "Не требуются"}</dd>
                  </div>
                  {presentation.gaps.length > 0 ? (
                    <div>
                      <dt>Недостающие данные</dt>
                      <dd>{presentation.gaps.map((gap, index) => <span key={`${gap}-${index}`}>{gap}</span>)}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>Источники</dt>
                    <dd>
                      <span>{presentation.sourceLabel}</span>
                      {presentation.sourceReferences.map((reference) => <span key={reference}>{reference}</span>)}
                    </dd>
                  </div>
                  <div><dt>План проверки</dt><dd>{presentation.validationPlan}</dd></div>
                  <div><dt>Что подтвердит</dt><dd>{presentation.confirmationGuidance}</dd></div>
                </dl>
              </details>
            </article>
          );
        }) : (
          <p className={styles.blocker}>Сценарных метрик пока нет. Отсутствующие факты не показываются как ноль.</p>
        )}
      </div>
    </section>
  );
}
