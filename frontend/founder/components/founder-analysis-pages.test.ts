import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { mergeCaseCopilotMetricCards } from "../lib/case-copilot-presentation.ts";
import {
  presentAcceptedDocumentGateState,
  presentCaseCopilotNoActionState,
  presentGate2ApprovalBlock,
} from "./founder-task-b-presentation.ts";

const component = readFileSync(
  new URL("./founder-analysis-pages.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("./founder-analysis-pages.module.css", import.meta.url),
  "utf8",
);
const shell = readFileSync(
  new URL("./founder-shell.tsx", import.meta.url),
  "utf8",
);
const controller = readFileSync(
  new URL("./founder-workspace-controller.tsx", import.meta.url),
  "utf8",
);

function metricCardSource(title: string): string {
  const start = component.indexOf(`title: "${title}"`);
  assert.notEqual(start, -1, `Expected metric card ${title} in founder-analysis-pages.tsx`);
  const end = component.indexOf("\n    }", start);
  assert.notEqual(end, -1, `Expected metric card ${title} object to be closed`);
  return component.slice(start, end);
}

test("exports the three approved analysis page ids and integration component", () => {
  for (const page of ["progress_gate2", "overview", "metrics"]) {
    assert.match(component, new RegExp(`"${page}"`, "u"));
    assert.match(
      component,
      new RegExp(`data-founder-analysis-page=[{"']${page.replaceAll("_", "-")}[}"']`, "u"),
    );
  }

  assert.match(component, /export type FounderAnalysisPageId/u);
  assert.match(component, /export type FounderAnalysisPagesProps/u);
  assert.match(component, /export function FounderAnalysisPages/u);
});

test("uses real profile, report, workflow data and callbacks", () => {
  assert.match(component, /StartupProfileResponse/u);
  assert.match(component, /StartupGtmResponse/u);
  assert.match(component, /StartupReportSnapshotResponse/u);
  assert.match(component, /buildFounderReportPresentation/u);
  assert.match(component, /workspace\?\.profile/u);
  assert.match(component, /workspace\?\.reportSnapshot/u);
  assert.match(component, /workspace\?\.stage/u);

  for (const callback of [
    "onGate2",
    "onGate3",
    "onOpenAdvisor",
    "onOpenMetrics",
    "onOpenMarket",
    "onOpenReport",
    "onAddEvidence",
  ]) {
    assert.match(component, new RegExp(callback, "u"));
  }

  assert.match(component, /workspace\?\.canApproveGate2 && hasDocumentReadEvidence\(workspace\)/u);
  assert.match(component, /onGate2\("approved"\)/u);
  assert.doesNotMatch(component, /onStartDeepAnalysis/u);
  assert.doesNotMatch(component, /workflowPanel|workflowDecisionPanel|WorkspaceActionPanel/u);
});

test("explains accepted-document progress without returning to awaiting-materials copy", () => {
  assert.match(component, /acceptedDocumentIds\?:\s*readonly string\[\]/u);
  assert.match(component, /lastKnownStatus\?:\s*string \| null/u);
  assert.match(component, /presentAcceptedDocumentGateState/u);
  assert.match(controller, /acceptedDocumentIds:\s*snapshot\?\.acceptedDocumentIds \?\? \[\]/u);
  assert.match(controller, /lastKnownStatus:\s*snapshot\?\.status\?\.analysis_status \?\? null/u);
});

test("disabled Gate 2 approval names the missing prerequisite and opens guided gap filling", () => {
  assert.match(component, /const gate2MissingPrerequisite = gate2ApprovalMissingPrerequisite\(workspace\)/u);
  assert.match(component, /presentGate2ApprovalBlock/u);
  assert.match(component, /data-gate2-prerequisite/u);
  assert.match(component, /Заполнить пропуски/u);
  assert.match(component, /onClick=\{onOpenAdvisor\}/u);
});

test("Gate 2 exposes a real online-research entry point through the consented case assistant", () => {
  const gate2Page = component.slice(
    component.indexOf("function ProgressGatePage"),
    component.indexOf("function OverviewPage"),
  );
  const gate2Integration = component.slice(
    component.indexOf('if (page === "progress_gate2")'),
    component.indexOf('if (page === "overview")'),
  );

  assert.match(gate2Page, /onOpenAdvisor\?: \(\) => void/u);
  assert.match(gate2Page, /onOpenResearch\?: \(\) => void/u);
  assert.match(gate2Page, /onClick=\{onOpenResearch\}[\s\S]*Онлайн-ресерч/u);
  assert.match(gate2Page, /явного согласия/u);
  assert.match(gate2Integration, /onOpenAdvisor=\{onOpenAdvisor\}/u);
  assert.match(gate2Integration, /onOpenResearch=\{onOpenResearch\}/u);
});

test("metrics public research source labels use collision-safe React keys", () => {
  assert.doesNotMatch(component, /sourceLabels\.map\(\(label\) => <li key=\{label\}>/u);
  assert.match(component, /sourceLabels\.map\(\(label, index\) => <li key=\{`source-label-\$\{index\}-\$\{label\}`\}>/u);
});

test("models accepted-document Gate 2 states from real product inputs", () => {
  const processing = presentAcceptedDocumentGateState({
    acceptedDocumentCount: 2,
    hasDocumentReadEvidence: false,
    lastKnownStatus: "primary_intake",
  });

  assert.equal(processing.documentCopy, "Документы приняты сервером");
  assert.equal(processing.documentStatus, "В процессе");
  assert.equal(processing.documentActive, true);
  assert.equal(processing.receiptTitle, "Документы приняты сервером · 2 файл(а)");
  assert.equal(
    processing.receiptDetail,
    "Идёт обработка принятых документов. Последний статус кейса: primary_intake",
  );
  assert.notEqual(processing.documentCopy, "Ожидает материалы");

  const evidenceReady = presentAcceptedDocumentGateState({
    acceptedDocumentCount: 1,
    hasDocumentReadEvidence: true,
    lastKnownStatus: "gate2_preview_ready",
  });

  assert.equal(evidenceReady.documentCopy, "Переданные материалы обработаны");
  assert.equal(evidenceReady.documentStatus, "Завершено");
  assert.equal(evidenceReady.documentActive, false);
  assert.equal(
    evidenceReady.receiptDetail,
    "Извлечение из принятого документа готово. Последний статус кейса: gate2_preview_ready",
  );

  const waiting = presentAcceptedDocumentGateState({
    acceptedDocumentCount: 0,
    hasDocumentReadEvidence: false,
    lastKnownStatus: null,
  });
  assert.equal(waiting.documentCopy, "Ожидает материалы");
  assert.equal(waiting.receiptTitle, null);
});

test("models disabled Gate 2 and Case Copilot recovery controls from behavior inputs", () => {
  const gate2 = presentGate2ApprovalBlock({
    acceptedDocumentCount: 1,
    canApproveGate2: false,
    hasDocumentReadEvidence: false,
  });

  assert.equal(gate2.disabledPrerequisite, "Нужно подтверждённое извлечение из принятого документа");
  assert.equal(gate2.repairLabel, "Исправить профиль");
  assert.equal(gate2.repairCopy, "Добавьте или замените документ, затем дождитесь первичного разбора.");

  const noAction = presentCaseCopilotNoActionState({
    answerActionCount: 0,
    busy: false,
    hasDocumentRequestHandler: true,
  });

  assert.equal(noAction.showAnswerControls, false);
  assert.equal(noAction.showPrimaryAnswerSubmit, false);
  assert.equal(noAction.showRecoveryAction, true);
  assert.equal(noAction.recoveryLabel, "Добавить документ");
  assert.equal(noAction.recoveryDisabled, false);
});

test("keeps founder-facing copy Russian, actionable, and free from raw internals", () => {
  for (const text of [
    "Анализ выполняется",
    "Этап 2",
    "Команда аналитических помощников",
    "Вот как я понял ваш стартап",
    "Метрики и финансы",
    "Что уже работает",
    "Что предлагает ИИ сейчас",
    "Если добавите",
    "Онлайн-ресерч использует только очищенные факты",
    "Готовность к росту",
    "Главная финансовая проблема",
  ]) {
    assert.match(component, new RegExp(text, "u"));
  }

  assert.doesNotMatch(
    component,
    /Алексей|\bMISSING\b|sha256:|profile_hash|snapshot_hash|source_hashes|parse_inventory|artifact_hash|locator_hash|prompt|chain-of-thought|local path/iu,
  );
});

test("explains generated growth terms in Russian and presents the idea stage readably", () => {
  for (const copy of [
    "ежемесячную регулярную выручку (MRR)",
    "отток клиентов",
    "ценность клиента (LTV)",
    "целевой сегмент (ICP)",
    "сигналы спроса",
    "темп расходов",
    "остаток денег",
    "запас времени",
  ]) {
    assert.match(component, new RegExp(copy.replace(/[()]/gu, "\\$&"), "u"));
  }

  assert.match(component, /formatFounderStage\(fieldValue\(workspace, "stage"/u);
  assert.doesNotMatch(
    component,
    /Если добавите traction|Если добавите ICP|Добавьте MRR"|Добавьте churn|Churn \+ средний чек|рассчитаю LTV"|Добавьте MRR и темп расходов/u,
  );
});

test("matches approved 03-05 desktop visual system through scoped css modules", () => {
  for (const selector of [
    ".page",
    ".hero",
    ".progressRail",
    ".gateCard",
    ".agentPanel",
    ".readinessGauge",
    ".overviewGrid",
    ".profileMap",
    ".metricCardsTop",
    ".metricsGrid",
    ".financePanel",
    ".financialProblem",
    ".pinkButton",
    ".glassPanel",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }

  assert.match(css, /grid-template-columns:\s*repeat\(7,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /border-radius:\s*(?:1[68]|2[26])px/u);
  assert.match(css, /linear-gradient\(135deg,\s*#f5a1cf/u);
  assert.doesNotMatch(css, /position:\s*fixed|width:\s*100vw|height:\s*100vh/u);
});

test("keeps 03 progress gate aligned to the approved 1586x992 desktop source viewport", () => {
  assert.match(component, /className=\{styles\.backgroundButton\}/u);
  assert.match(component, /Работать в фоне/u);
  assert.match(component, /className=\{styles\.gateBadge\}/u);
  assert.match(component, /className=\{styles\.gateConfidence\}/u);
  assert.match(css, /\.hero\s*\{[\s\S]*?background:\s*transparent/u);
  assert.match(css, /\.hero h1\s*\{[\s\S]*?font-size:\s*clamp\(28px,\s*2\.15vw,\s*38px\)/u);
  assert.match(css, /\.backgroundButton\s*\{[\s\S]*?min-height:\s*48px/u);
  assert.match(css, /\.progressRail\s*\{[\s\S]*?min-height:\s*96px/u);
  assert.match(css, /\.progressLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(500px,\s*0\.92fr\)\s+minmax\(0,\s*1\.08fr\)/u);
  assert.match(css, /\.gateBadge\s*\{[\s\S]*?min-inline-size:\s*52px/u);
  assert.match(css, /\.gateConfidence\s*\{[\s\S]*?color:\s*var\(--analysis-green\)/u);
  assert.match(css, /\.agentRow\s*\{[\s\S]*?grid-template-columns:\s*48px\s+minmax\(0,\s*1fr\)\s+116px/u);
  assert.match(css, /\.gateProfile div\s*\{[\s\S]*?grid-template-columns:\s*150px\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.agentRow > div:not\(\.iconBubble\)\s*\{[\s\S]*?display:\s*grid[\s\S]*?gap:\s*3px/u);
  assert.match(css, /\.agentRow strong,\s*\n\.agentRow span\s*\{[\s\S]*?display:\s*block[\s\S]*?line-height:\s*1\.16/u);
  assert.match(css, /\.actionStrip\s*\{[\s\S]*?display:\s*flex/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.progressRail\s*\{[\s\S]*?min-height:\s*114px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentPanel\s*\{[\s\S]*?min-height:\s*638px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.gateCard\s*\{[\s\S]*?display:\s*flex[\s\S]*?min-height:\s*556px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.gateCard\s+\.actionStrip\s*\{[\s\S]*?margin-top:\s*auto/u,
  );
  assert.match(component, /\? "Нужно решение"/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.heroAside\s*>\s*\.statusPill\s*\{[\s\S]*?display:\s*inline-flex/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRow\s+\.tone_green\s*\{[\s\S]*?background:\s*rgba\(139,\s*217,\s*140,\s*0\.14\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRow\s+em\s*\{[\s\S]*?white-space:\s*nowrap/u,
  );
  assert.doesNotMatch(css, /\.gateProfile div,\s*\n\.metricCard,\s*\n\.problemAction,\s*\n\.suggestionRow\s*\{/u);
});

test("matches the approved 03 type, status, icon, and surface hierarchy without fake progress", () => {
  for (const icon of [
    "ChartNoAxesColumnIncreasing",
    "Clock3",
    "FileText",
    "Hourglass",
    "LoaderCircle",
    "UserRound",
  ]) {
    assert.match(component, new RegExp(icon, "u"));
  }

  assert.match(shell, /data-founder-active-view=\{activeView\}/u);
  assert.match(component, /statusIcon:\s*LucideIcon/u);
  assert.match(component, /progress:\s*Readonly<\{/u);
  assert.match(component, /className=\{styles\.agentProgress\}/u);
  assert.match(component, /className=\{styles\.agentProgressTrack\}/u);
  assert.match(component, /data-tone=\{tone\}/u);
  assert.match(component, /statusA11y:\s*isAwaitingGate2\s*\?\s*"Ожидает решения на этапе 2"\s*:\s*undefined/u);
  assert.match(component, /status:\s*hasDeepAnalysis \? "Результат доступен" : isAwaitingGate2 \? "Ждёт решения на этапе 2" : "В очереди"/u);
  assert.match(component, /aria-label=\{statusA11y\}/u);
  assert.match(component, /stageProgressSummary\(stage\)/u);
  assert.ok(component.includes("`${progress.completed} из ${gateSteps.length} этапов завершено`"));
  assert.doesNotMatch(component, /2 из 7 этапов завершено/u);
  assert.doesNotMatch(component, /value:\s*29/u);
  assert.doesNotMatch(component, /63%/u);

  assert.doesNotMatch(
    css,
    /:global\(\.founder-dashboard-shell\[data-founder-active-view="progress_gate2"\]\)/u,
  );
  assert.match(css, /\.progressGate2Shell\s*\{[\s\S]*?--fi-sidebar-width:\s*254px;[\s\S]*?--fi-content-gap:\s*28px;/u);
  assert.match(shell, /analysisStyles\.progressGate2Shell/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s*\{[\s\S]*?font-family:\s*"Segoe UI"/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.hero\s+\.eyebrow\s*\{[\s\S]*?display:\s*none/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.progressLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(470px,\s*0\.78fr\)\s+minmax\(0,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentProgressTrack\s*\{[\s\S]*?block-size:\s*5px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.gateBadge\s*\{[\s\S]*?border:\s*0;[\s\S]*?border-radius:\s*0/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.actionStrip\s+\.pinkButton\s*\{[\s\S]*?min-height:\s*60px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.safeBanner\s+strong\s*\{[\s\S]*?font-weight:\s*400/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRow\s+strong\s*\{[\s\S]*?font-weight:\s*400/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.actionStrip\s+\.pinkButton\s*\{[\s\S]*?font-weight:\s*400/u,
  );
});

test("propagates selected scenarios into founder-facing metric cards and chart context without source promotion", () => {
  assert.match(component, /ScenarioProjectionResponse/u);
  assert.match(component, /StartupScenarioMetric/u);
  assert.match(component, /StartupScenarioVariant/u);
  assert.match(component, /scenarios\?:\s*ScenarioProjectionResponse \| null/u);
  assert.match(component, /selectedScenario\?:\s*StartupScenarioVariant \| null/u);
  assert.match(component, /function scenarioMetricCards/u);
  assert.match(component, /buildFounderScenarioMetricChartPresentation/u);
  assert.match(component, /buildFounderScenarioReadinessPresentation/u);
  assert.match(component, /data-scenario-chart-projection/u);
  assert.match(component, /workspace\?\.selectedScenario/u);
  assert.match(component, /selectedScenario\.metrics/u);
  assert.match(component, /presentScenarioMetric/u);
  assert.match(component, /presentation\?:\s*FounderScenarioMetricPresentation/u);
  assert.match(component, /presentation\.title/u);
  assert.match(component, /presentation\.value/u);
  assert.match(component, /presentation\.trustStatement/u);
  assert.match(component, /<summary>Как рассчитано и проверить<\/summary>/u);
  assert.match(component, /presentation\.formula/u);
  assert.match(component, /presentation\.dependencies\.map/u);
  assert.match(component, /presentation\.sourceReferences\.map/u);
  assert.match(component, /presentation\.validationPlan/u);
  assert.match(component, /confirmationGuidance/u);
  assert.doesNotMatch(component, /Scenario-only/u);
  assert.doesNotMatch(component, /Публичный benchmark/u);
  assert.match(component, /formatScenario\(workspace\?\.selectedScenario\.scenario_key\)/u);
  assert.doesNotMatch(component, /scenarioChart\.points\.map/u);
  assert.match(component, /scenarioReadinessCards\[0\]/u);
  assert.doesNotMatch(component, /provenance:\s*"source_fact"/u);
});

test("keeps confirmed actual metric cards primary when a scenario has the same slot", () => {
  const cards = mergeCaseCopilotMetricCards(
    [
      { slot: "mrr", status: "source_fact", title: "MRR", value: "$101,000" },
      { slot: "arr", status: "needs", title: "ARR", value: "расчёт по MRR" },
    ],
    [
      { slot: "mrr", status: "deterministic_calculation", title: "MRR", value: "700000–900000 KZT/month" },
    ],
  );

  assert.deepEqual(cards.map((card) => [card.slot, card.status, card.value]), [
    ["mrr", "source_fact", "$101,000"],
    ["arr", "needs", "расчёт по MRR"],
  ]);
});

test("renders the approved 03 role icons and one continuous dotted agent route", () => {
  assert.match(component, /type Gate2AgentIconTone = "document" \| "profile" \| "metrics" \| "market" \| "risk" \| "gtm"/u);
  assert.match(component, /type Gate2AgentRouteTone = "complete" \| "active" \| "queued"/u);
  assert.match(component, /iconTone:\s*Gate2AgentIconTone/u);
  assert.match(component, /routeTone:\s*Gate2AgentRouteTone/u);
  assert.match(component, /className=\{styles\.agentRouteNode\}/u);
  assert.match(component, /data-route-tone=\{routeTone\}/u);
  assert.match(component, /iconTone=\{iconTone\}/u);
  assert.doesNotMatch(component, /<b aria-hidden="true" \/>/u);

  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentTimeline\s*\{[\s\S]*?position:\s*relative/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentTimeline::before\s*\{[\s\S]*?border-inline-start:\s*1px dashed/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRouteNode\s*\{[\s\S]*?border-radius:\s*999px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRow\s+\.iconBubble\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?block-size:\s*48px;[\s\S]*?display:\s*inline-flex;[\s\S]*?inline-size:\s*48px;[\s\S]*?justify-content:\s*center;[\s\S]*?line-height:\s*0;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="progress-gate2"\]\s+\.agentRow\s+\.iconBubble svg\s*\{[\s\S]*?display:\s*block;[\s\S]*?flex:\s*0 0 auto;[\s\S]*?margin:\s*0;/u,
  );

  for (const iconTone of ["document", "profile", "metrics", "market", "risk", "gtm"]) {
    assert.match(css, new RegExp(`\\.agentIcon_${iconTone}\\s*\\{`, "u"));
  }
});

test("fits owner-review screens 03 and 04 into one 1440x1000 composition", () => {
  assert.match(component, /function analysisProgressStage/u);
  assert.match(
    component,
    /if \(stage === "primary_ready"\) \{[\s\S]*?return \{ active: 1, completedThrough: 0, current: 2 \};/u,
  );
  assert.match(component, /Шаг \{analysisProgress\.current\} из 7/u);
  assert.match(
    component,
    /className=\{styles\.gateColumn\}[\s\S]*?className=\{`\$\{styles\.glassPanel\} \$\{styles\.gateCard\}`\}[\s\S]*?className=\{styles\.searchStatus\}[\s\S]*?<section className=\{styles\.safeBanner\}/u,
  );
  assert.doesNotMatch(component, /Лучший вопрос AI/u);

  assert.match(css, /\.progressLayout\s*\{[\s\S]*?align-items:\s*start/u);
  assert.match(css, /\.gateColumn\s*\{[\s\S]*?display:\s*grid;[\s\S]*?gap:\s*10px/u);
  assert.match(css, /\.agentRow\s*\{[\s\S]*?min-height:\s*68px/u);
  assert.match(css, /\.gateProfile div\s*\{[\s\S]*?min-height:\s*44px/u);
  assert.match(css, /\.readinessTop > \*\s*\{[\s\S]*?min-height:\s*190px/u);
  assert.match(css, /\.gaugeArc\s*\{[\s\S]*?aspect-ratio:\s*2\s*\/\s*1/u);
  assert.match(css, /\.gaugeArc\s*\{[\s\S]*?inline-size:\s*min\(100%,\s*300px\)/u);
  assert.match(css, /\.evidenceItem\s*\{[\s\S]*?min-height:\s*72px/u);
  assert.match(css, /\.suggestionRow\s*\{[\s\S]*?min-height:\s*64px/u);
});

test("keeps the overview evidence, recommendations, and next-data strip above the 1000px fold", () => {
  assert.match(
    component,
    /className=\{styles\.overviewDisclaimer\}[\s\S]*?Оценка помогает расставить приоритеты и не является инвестиционной рекомендацией\./u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s*\{[\s\S]*?--analysis-panel:\s*rgba\(18,\s*18,\s*20,\s*0\.88\);[\s\S]*?gap:\s*10px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessTop\s*>\s*\*\s*\{[\s\S]*?min-height:\s*188px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.profileMap\s*\{[\s\S]*?min-height:\s*300px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.evidenceItem\s*\{[\s\S]*?grid-template-columns:\s*44px\s+minmax\(0,\s*1fr\);[\s\S]*?min-height:\s*78px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.suggestionRow\s*\{[\s\S]*?min-height:\s*70px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.addDataStrip button\s*\{[\s\S]*?min-height:\s*60px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.overviewDisclaimer\s*\{[\s\S]*?min-height:\s*24px/u,
  );
});

test("matches the approved screen 04 dashboard hierarchy with truthful data", () => {
  assert.match(component, /className=\{styles\.circleMetricBody\}/u);
  assert.match(component, /className=\{styles\.circleMetricCopy\}/u);
  assert.match(component, /icon:\s*MessageSquareText/u);
  assert.match(component, /icon:\s*Target/u);
  assert.match(component, /icon:\s*TriangleAlert/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessTop\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.75fr\)\s+minmax\(0,\s*0\.82fr\)\s+minmax\(0,\s*0\.95fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessTop\s*>\s*\*\s*\{[\s\S]*?block-size:\s*auto[\s\S]*?overflow:\s*visible/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.overviewGrid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*0\.95fr\)\s+minmax\(360px,\s*1\.18fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeCaption\s*\{[\s\S]*?position:\s*static;[\s\S]*?text-align:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.addDataStrip button\s*>\s*svg\s*\{[\s\S]*?block-size:\s*40px;[\s\S]*?inline-size:\s*40px/u,
  );
});

test("polishes screen 04 charts and explains each AI suggestion without invented claims", () => {
  assert.match(component, /function SemicircleGauge/u);
  assert.match(component, /function DonutMetric/u);
  assert.match(component, /pathLength="100"/u);
  assert.match(component, /strokeLinecap="round"/u);
  assert.match(component, /className=\{styles\.suggestionTitleLine\}/u);
  assert.match(component, /className=\{styles\.suggestionIssue\}/u);
  assert.match(component, /className=\{styles\.suggestionAction\}/u);
  assert.match(component, /Сегмент, роль покупателя и бюджет требуют подтверждения\./u);
  assert.match(component, /Добавьте этапы и конверсии — я найду узкое место и первый тест\./u);

  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.overviewHeroActions\s+\.outlineButton\s*\{[\s\S]*?background:\s*linear-gradient\([\s\S]*?font-size:\s*14px;[\s\S]*?font-weight:\s*500;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeTrack\s*\{[\s\S]*?stroke:\s*rgba\(255,\s*222,\s*240,\s*0\.1\);[\s\S]*?stroke-width:\s*13;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeProgress\s*\{[\s\S]*?filter:\s*drop-shadow\(0 7px 12px rgba\(245,\s*161,\s*207,\s*0\.18\)\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.circularMetricRing\s*\{[\s\S]*?inline-size:\s*88px;[\s\S]*?min-block-size:\s*88px;[\s\S]*?position:\s*relative;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.suggestionRow\s+em\s*\{[\s\S]*?font-weight:\s*500;[\s\S]*?text-transform:\s*none;/u,
  );
});

test("keeps the screen 04 readiness score and explanation in a calm non-overlapping stack", () => {
  assert.match(component, /className=\{styles\.gaugeStage\}/u);
  assert.match(component, /className=\{styles\.gaugeCaption\}/u);
  assert.match(component, /Пока нет документальных данных для оценки\./u);
  assert.match(component, /Добавьте материалы — я соберу выводы\./u);

  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeStage\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-rows:\s*auto auto;[\s\S]*?position:\s*relative;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeArc\s*\{[\s\S]*?block-size:\s*146px;[\s\S]*?position:\s*relative;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeValue\s*\{[\s\S]*?inset-block-start:\s*48px;[\s\S]*?font-variant-numeric:\s*tabular-nums;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeCaption\s*\{[\s\S]*?position:\s*static;[\s\S]*?text-wrap:\s*balance;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessGauge\s*>\s*span\s*\{[\s\S]*?font-size:\s*14px;[\s\S]*?font-weight:\s*400;/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.gaugeCaption\s*\{[\s\S]*?font-size:\s*13px;[\s\S]*?line-height:\s*1\.34;/u,
  );
  assert.doesNotMatch(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessGauge\s*>\s*p/u,
  );
});

test("derives Gate 2 agent states from the real workflow stage without invented progress", () => {
  assert.match(component, /function gate2AgentRows/u);
  assert.match(component, /function hasSourceBackedPrimaryProfile/u);
  assert.match(component, /const requiredPrimaryProfileFields/u);
  for (const fieldName of [
    "startup_name",
    "one_line_description",
    "problem",
    "icp",
    "pricing_revenue_model",
    "stage",
  ]) {
    assert.match(component, new RegExp(`"${fieldName}"`, "u"));
  }
  assert.match(component, /requiredPrimaryProfileFields\.every\(\(fieldName\)/u);
  assert.match(component, /function stageProgressSummary/u);
  assert.match(component, /function profileConfidenceScore/u);
  assert.match(component, /workspace\?\.stage/u);
  assert.match(component, /workspace\?\.profile/u);
  assert.match(component, /Ожидает решения на этапе 2/u);
  assert.match(component, /field\.status === "source_fact"/u);
  assert.match(component, /field\.values\.length > 0/u);
  assert.match(component, /field\.evidence_refs\.length > 0/u);
  assert.doesNotMatch(component, /field\.status !== "insufficient_data"/u);
  assert.doesNotMatch(component, /sourceFactFieldCount \+ inferredFieldCount \+ contradictionFieldCount/u);
  assert.doesNotMatch(component, /Math\.max\(\s*32/u);
  assert.doesNotMatch(component, /progressPercentLabel/u);
  assert.doesNotMatch(component, /Ожидает разрешения на внешний поиск/u);
});

test("keeps Gate 2 approval and confidence source-backed across every required core field", () => {
  assert.match(component, /function isSourceFactWithEvidence/u);
  assert.match(component, /function hasDocumentReadEvidence/u);
  assert.match(component, /Object\.values\(fields\)\.some\(isSourceFactWithEvidence\)/u);
  assert.match(component, /requiredPrimaryProfileFields\.reduce\(\(total, fieldName\)/u);
  assert.match(component, /sourceConfidenceWeight\(fields\[fieldName\]\?\.confidence\)/u);
  assert.match(component, /const numericConfidence = Number\(confidence\)/u);
  assert.match(component, /Number\.isFinite\(numericConfidence\)/u);
  assert.match(component, /Math\.min\(1, Math\.max\(0, numericConfidence\)\)/u);
  assert.match(component, /Math\.round\(\(coveredCoreWeight \/ requiredPrimaryProfileFields\.length\) \* 100\)/u);
  assert.doesNotMatch(component, /70% по подтверждённым полям/u);
  assert.doesNotMatch(component, /70%/u);
});

test("renders profile coverage from covered fields instead of reusing confidence", () => {
  assert.match(component, /const profileCoverage = profileCoverageStats\(workspace\)/u);
  assert.match(component, /const profileCoverageScore = profileCoverage\?\.coveragePercent \?\? null/u);
  assert.doesNotMatch(component, /const profileCoverageScore = profileConfidenceScore\(workspace\)/u);
});

test("renders a founder-safe document-understood summary with facts or explicit gaps", () => {
  assert.match(component, /type DocumentUnderstoodRow/u);
  assert.match(component, /function documentUnderstoodRows/u);
  assert.match(component, /Документ понял так/u);
  assert.match(component, /documentUnderstoodRows\(workspace\)\.map/u);
  for (const label of ["Продукт", "Клиент", "Проблема", "Монетизация", "Стадия"]) {
    assert.match(component, new RegExp(`label: "${label}"`, "u"));
  }
  assert.match(component, /statusLabel: "Заявлено в документе"/u);
  assert.match(component, /statusLabel: "Гипотеза — подтвердите"/u);
  assert.match(component, /statusLabel: "Противоречие — нужно решение"/u);
  assert.match(component, /statusLabel: "Нужно заполнить"/u);
  assert.match(component, /Не найдено в документе — опишите продукт одной строкой/u);
  assert.match(component, /Не найдено в документе — укажите боль клиента/u);
  assert.match(component, /Не найдено в документе — укажите, кто и за что платит/u);
  assert.doesNotMatch(component, /artifact_hash|locator_hash|fragment_id|reason_code|parse_inventory|source_hashes/u);
});

test("keeps 04 and 05 desktop-dense, separated, and free from raw producer values", () => {
  assert.match(component, /className=\{styles\.overviewHeroActions\}/u);
  assert.match(component, /className=\{styles\.growthStagePill\}/u);
  assert.match(component, /className=\{styles\.updatedBadge\}/u);
  assert.match(component, /className=\{styles\.circularMetricRing\}/u);
  assert.match(component, /className=\{styles\.addDataCtaPane\}/u);
  assert.match(component, /className=\{styles\.metricsToolbar\}/u);
  assert.match(component, /className=\{styles\.projectSelect\}/u);
  assert.match(component, /<h2>Динамика ежемесячной регулярной выручки \(MRR\)<\/h2>/u);
  assert.match(component, /className=\{styles\.chartContext\}/u);
  assert.match(css, /\.overviewHeroActions\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(520px,\s*0\.72fr\)/u);
  assert.match(css, /\.growthStagePill\s*\{[\s\S]*?border-color:\s*var\(--analysis-border-hot\)/u);
  assert.match(css, /\.updatedBadge\s*\{[\s\S]*?min-height:\s*38px/u);
  assert.match(css, /\.page\[data-founder-analysis-page="overview"\]\s+\.donutProgress\s*\{[\s\S]*?stroke:\s*var\(--analysis-pink\)/u);
  assert.match(css, /\.addDataCtaPane\s*\{[\s\S]*?border-inline-start:\s*1px dashed/u);
  assert.match(css, /\.metricsToolbar\s*\{[\s\S]*?grid-template-columns:\s*220px\s+max-content/u);
  assert.match(css, /\.projectSelect\s*\{[\s\S]*?min-height:\s*42px/u);
  assert.match(css, /\.overviewGrid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*0\.95fr\)\s+minmax\(0,\s*0\.95fr\)\s+minmax\(320px,\s*0\.85fr\)/u);
  assert.match(css, /\.profileMap\s*\{[\s\S]*?min-height:\s*300px/u);
  assert.match(css, /\.evidenceItem > div\s*\{[\s\S]*?display:\s*grid[\s\S]*?gap:\s*4px/u);
  assert.match(css, /\.evidenceItem strong,\s*\n\.evidenceItem span\s*\{[\s\S]*?display:\s*block[\s\S]*?line-height:\s*1\.2/u);
  assert.match(css, /\.addDataStrip button span,\s*\n\.addDataStrip button div,[\s\S]*?\.addDataCtaPane\s*\{[\s\S]*?display:\s*grid/u);
  assert.match(component, /\\\\bunknown\\\\b/u);
  assert.match(component, /\\\\b\[a-z\]\[a-z0-9\]\+\(\?:_\[a-z0-9\]\+\)\+\\\\s\*:/u);
  assert.match(component, /Нет документальных наблюдений ежемесячной выручки \(MRR\)/u);
  assert.match(component, /metricDashboard\.summary\.title/u);
  assert.match(component, /metricDashboard\.summary\.detail/u);
  assert.doesNotMatch(component, /Без MRR и burn нельзя сравнить рост выручки с расходами/u);
  assert.doesNotMatch(component, /churn_reduction: 42|Рост есть, но его недостаточно|Расходы растут быстрее регулярной выручки|\$24k|\$20k|\$16k|\$12k|\$8k|\$4k|\$0/u);
});

test("uses the approved desktop panel rhythm across overview and metrics", () => {
  assert.match(
    css,
    /\.glassPanel,[\s\S]*?\.addDataStrip\s*\{[\s\S]*?border-radius:\s*16px;[\s\S]*?box-shadow:\s*0 16px 54px rgba\(0, 0, 0, 0\.2\);/u,
  );
  assert.match(
    css,
    /\.agentPanel,[\s\S]*?\.financialProblem\s*\{[\s\S]*?padding:\s*20px;/u,
  );
  assert.match(css, /\.evidenceItem\s*\{[\s\S]*?min-height:\s*72px/u);
  assert.match(css, /\.metricCard\s*\{[\s\S]*?min-height:\s*170px/u);
  assert.match(css, /\.chartCard\s*\{[\s\S]*?border-radius:\s*16px;[\s\S]*?min-height:\s*330px/u);
});

test("derives the metrics chart from producer data and leaves every primary CTA actionable", () => {
  assert.match(component, /buildFounderMetricDashboardPresentation/u);
  assert.match(
    component,
    /metricCards\(\s*metricDashboard\.cards,\s*metricDashboard\.contradictions,\s*scenarioMetricCards\(workspace\?\.selectedScenario \?\? null\),\s*\)/u,
  );
  assert.match(component, /metricDashboard\.mrrSeries/u);
  assert.match(component, /chartMaximum/u);
  assert.match(component, /founderChartBarWidth/u);
  assert.match(component, /metricChartPoints\.map/u);
  assert.doesNotMatch(component, /const hasVerifiedMrr = false/u);
  assert.doesNotMatch(component, /\(\(point \+ index\) % 4\) \* 6/u);
  assert.doesNotMatch(component, /className=\{styles\.problemAction\} key=\{action\} type="button"/u);
  assert.match(component, /className=\{styles\.problemAction\}[\s\S]*?disabled=\{!onAddEvidence\}[\s\S]*?key=\{action\}[\s\S]*?onClick=\{onAddEvidence\}[\s\S]*?type="button"/u);
  assert.match(component, /<button[\s\S]*?className=\{styles\.pinkButton\}[\s\S]*?data-founder-action=\{action\}[\s\S]*?disabled=\{!onClick\}[\s\S]*?onClick=\{onClick\}[\s\S]*?type="button"/u);
  assert.match(component, /<button className=\{styles\.outlineButton\} disabled=\{!onClick\} onClick=\{onClick\} type="button">/u);
  assert.match(
    css,
    /\.pinkButton:disabled,\s*\n\.outlineButton:disabled,[\s\S]*?\{[\s\S]*?cursor:\s*not-allowed[\s\S]*?opacity:\s*0\.4/u,
  );
});

test("renders 05 metrics as an accessible line-chart dashboard, not a raw evidence list", () => {
  assert.match(component, /className=\{styles\.mrrLineChart\}/u);
  assert.match(component, /role="img"/u);
  assert.match(component, /aria-label="Динамика ежемесячной регулярной выручки по значениям из документов"/u);
  assert.match(component, /aria-label=\{`Точка ежемесячной регулярной выручки \$\{point\.label\}: \$\{point\.displayValue\}`\}/u);
  assert.match(component, /Интерпретация динамики зависит от темпа расходов и запаса денег/u);
  assert.doesNotMatch(component, /MRR point|\bburn\b/iu);
  assert.match(component, /metricChartPoints/u);
  assert.match(component, /metricChartPoints\.map\(\(point, index\)/u);
  assert.match(component, /className=\{styles\.linePoint\}/u);
  assert.match(component, /className=\{styles\.lineSegment\}/u);
  assert.match(component, /className=\{styles\.xAxisLabel\}/u);
  assert.match(component, /className=\{styles\.yAxisLabel\}/u);
  assert.match(component, /aria-label=\{`Точка ежемесячной регулярной выручки \$\{point\.label\}: \$\{point\.displayValue\}`\}/u);
  assert.doesNotMatch(component, /confirmedMetricsChart \? \(\s*<div className=\{styles\.evidenceList\}>/u);
  assert.doesNotMatch(component, /\b(?:Jan|Feb|Mar|Apr|May|Jun)\b|\$24k|\$20k|\$16k|\$12k|\$8k|\$4k|\$0/u);

  for (const selector of [
    ".periodPills",
    ".periodPill",
    ".mrrLineChart",
    ".chartPlot",
    ".lineSegment",
    ".linePoint",
    ".xAxisLabel",
    ".yAxisLabel",
    ".chartFootnote",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }
});

test("keeps 05 metrics card statuses and problem panel actions visually close to the approved mockup", () => {
  assert.match(component, /metricStatusCopy/u);
  assert.match(component, /styles\.metricStatus/u);
  assert.match(component, /styles\[`metricStatus_\$\{card\.tone\}`\]/u);
  assert.match(component, /aria-label=\{`\$\{card\.title\}: \$\{card\.value\}\. \$\{metricStatusCopy\(card\.tone, card\.status\)\}`\}/u);
  assert.match(component, /3M/u);
  assert.match(component, /6M/u);
  assert.match(component, /12M/u);
  assert.match(component, /Что можно сделать прямо сейчас/u);
  assert.match(component, /Могу помочь собрать шаблон/u);
  assert.match(component, /problemActions/u);
  assert.match(component, /problemActions\.map/u);
  assert.match(component, /aria-label=\{`Финансовое действие: \$\{action\}`\}/u);

  for (const selector of [
    ".metricStatus",
    ".metricStatus_green",
    ".metricStatus_amber",
    ".metricStatus_pink",
    ".problemActions",
    ".templateButton",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }
});

test("keeps 05 metrics readable in the approved desktop composition when financial data is still missing", () => {
  assert.match(
    component,
    /className=\{styles\.sparkline\}[\s\S]*?data-empty=\{cardSeries\.length === 0\}[\s\S]*?aria-label=\{cardSeries\.length === 0\s*\? "Нет документального ряда для мини-графика"/u,
  );
  assert.match(
    component,
    /<\/section>\s*<footer aria-label="Как читать статусы метрик" className=\{styles\.legend\}>[\s\S]*?<\/footer>\s*<\/section>/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.hero\s+\.eyebrow\s*\{[\s\S]*?display:\s*none/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.hero h1\s*\{[\s\S]*?font-size:\s*34px;[\s\S]*?font-weight:\s*400/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCard\s*\{[\s\S]*?grid-template-rows:\s*none;[\s\S]*?min-height:\s*auto;[\s\S]*?overflow:\s*visible/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.sparkline\[data-empty="true"\]\s*\{[\s\S]*?border-block-end:\s*1px dashed/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.legend\s*\{[\s\S]*?min-height:\s*38px;[\s\S]*?padding:\s*2px 6px 0/u,
  );
});

test("explains 05 metric provenance statuses with distinct icons, labels, and readable copy", () => {
  assert.match(component, /<footer aria-label="Как читать статусы метрик" className=\{styles\.legend\}>/u);
  assert.match(
    component,
    /className=\{styles\.legendItem\} data-tone="fact"[\s\S]*?Заявлено в загруженных файлах; это не независимая проверка/u,
  );
  assert.match(
    component,
    /className=\{styles\.legendItem\} data-tone="calculated"[\s\S]*?Получено на основе модели и допущений/u,
  );
  assert.match(
    component,
    /className=\{styles\.legendItem\} data-tone="hypothesis"[\s\S]*?Нужны дополнительные данные для проверки/u,
  );
  assert.match(component, /className=\{styles\.legendIcon\}/u);
  assert.match(component, /className=\{styles\.legendCopy\}/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.legend\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\);[\s\S]*?min-height:\s*38px/u,
  );
  for (const tone of ["fact", "calculated", "hypothesis"] as const) {
    assert.match(css, new RegExp(`\\.legendItem\\[data-tone="${tone}"\\]`, "u"));
  }
});

test("metrics page surfaces accepted online research and scenario metric deltas outside the side panel", () => {
  assert.match(component, /ResearchJobResponse/u);
  assert.match(component, /ScenarioMetricComparison/u);
  assert.match(component, /researchJob\?:\s*ResearchJobResponse \| null/u);
  assert.match(component, /researchMetricComparison\?:\s*ScenarioMetricComparison \| null/u);
  assert.match(component, /const researchSummary = buildMetricsResearchSummary\(workspace\)/u);
  assert.match(component, /data-metrics-research-summary/u);
  assert.match(component, /Онлайн-ресерч обновил сценарные метрики/u);
  assert.match(component, /Публичные источники не заполняют MRR, выручку, расходы, деньги и клиентские факты/u);
  assert.match(component, /researchSummary\.changedMetrics\.map/u);
  assert.match(component, /formatMetricDeltaValue\(change\.oldValue\)[\s\S]*formatMetricDeltaValue\(change\.newValue\)/u);
  assert.match(css, /\.metricsResearchSummary\s*\{/u);
  assert.match(css, /\.metricsDeltaList\s*\{/u);
});

test("uses document-stated wording for source facts instead of independent confirmation", () => {
  for (const expected of [
    "Заявлено в документе",
    'status: "Заявлено"',
    "Профиль собран из полей, заявленных в документах",
    "Заявлено в загруженных файлах; это не независимая проверка",
    "по значениям из документов",
    "Нет документального ряда для мини-графика",
  ]) {
    assert.match(component, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "u"));
  }
  assert.doesNotMatch(component, /status: "Факт"|Факт из документа|Профиль собран из подтвержд[её]нных полей|Подтвержд[её]нные данные из ваших файлов|подтвержд[её]нным данным|Нет подтвержд[её]нного ряда/u);
});

test("fits the truthful metrics empty state and both data actions into the 1440x1000 owner frame", () => {
  assert.match(
    component,
    /<OutlineButton onClick=\{onOpenAdvisor\}>[\s\S]*?Объяснить любую метрику[\s\S]*?<\/OutlineButton>/u,
  );
  assert.match(
    component,
    /<PinkButton onClick=\{onOpenAdvisor\}>\s*Построить сценарии[\s\S]*?<\/PinkButton>\s*<\/section>\s*<\/div>\s*<section className=\{styles\.addDataStrip\}>/u,
  );
  assert.doesNotMatch(component, /onClick=\{onOpenReport\}>[\s\S]{0,180}(?:Объяснить любую метрику|Построить сценарии)/u);
  assert.match(
    component,
    /<span className=\{styles\.addDataCtaPane\}>[\s\S]*?Добавить данные[\s\S]*?Могу помочь собрать шаблон/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s*\{[\s\S]*?--analysis-panel:\s*rgba\(18,\s*18,\s*20,\s*0\.88\);[\s\S]*?gap:\s*10px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCard\s*\{[\s\S]*?min-height:\s*auto;[\s\S]*?overflow:\s*visible/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCard p\s*\{[\s\S]*?font-size:\s*11\.5px;[\s\S]*?line-height:\s*1\.38/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.chartCard\s*\{[\s\S]*?min-height:\s*246px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartState\s*\{[\s\S]*?min-height:\s*202px/u,
  );
  assert.match(component, /className=\{styles\.emptyChartSkeleton\}/u);
  assert.match(component, /className=\{styles\.emptyChartBaseline\}/u);
  assert.match(component, /className=\{styles\.emptyChartPeriods\}/u);
  assert.match(component, /className=\{styles\.emptyChartCopy\}/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartSkeleton\s*\{[\s\S]*?repeating-linear-gradient[\s\S]*?min-height:\s*128px/u,
  );
  assert.match(css, /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartCopy p\s*\{[\s\S]*?margin:\s*0;[\s\S]*?max-inline-size:\s*none/u);
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartBaseline\s*\{[\s\S]*?linear-gradient\(90deg,\s*transparent,\s*rgba\(245,\s*161,\s*207,\s*0\.32\),\s*transparent\)/u,
  );
  assert.match(css, /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartPeriods\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*1fr\)/u);
});

test("uses the owner-approved 04-05 vertical rhythm instead of leaving the lower canvas underfilled", () => {
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.readinessTop\s*>\s*\*\s*\{[\s\S]*?min-height:\s*188px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.profileMap\s*\{[\s\S]*?min-height:\s*300px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="overview"\]\s+\.addDataStrip\s*\{[\s\S]*?min-height:\s*112px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCard\s*\{[\s\S]*?min-height:\s*auto/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricsGrid\s*>\s*\*\s*\{[\s\S]*?min-height:\s*344px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.chartCard\s*\{[\s\S]*?min-height:\s*246px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.emptyChartState\s*\{[\s\S]*?min-height:\s*202px/u,
  );
});

test("fails closed on overview scores and claims until canonical report evidence exists", () => {
  assert.match(component, /function profileSignalCard/u);
  assert.match(component, /function profileCoverageStats/u);
  assert.match(component, /function reportIssueCard/u);
  assert.match(component, /status === "source_fact"/u);
  assert.match(component, /status === "inference"/u);
  assert.match(component, /status === "contradiction"/u);
  assert.match(component, /const profileCoverage = profileCoverageStats\(workspace\)/u);
  assert.match(component, /const readinessScore = workspace\?\.reportSnapshot\s*\?\s*Math\.round/u);
  assert.match(component, /const evidenceScore = workspace\?\.reportSnapshot\s*\?\s*Math\.round/u);
  assert.doesNotMatch(component, /Math\.max\(\s*12,\s*Math\.round/u);
  assert.doesNotMatch(component, /Math\.max\(18,\s*Math\.round/u);
  assert.doesNotMatch(component, /Math\.min\(92, readinessScore \+ 14\)/u);
  assert.doesNotMatch(component, /Ранний рост|Анализ обновлён сегодня|Есть признаки спроса|Критично|Высокий риск/u);
  assert.doesNotMatch(component, /B2B SaaS или другой проект|Рост есть, но решение зависит/u);
  assert.doesNotMatch(component, /title: "MRR",[\s\S]*?value: fieldValue\(workspace, "traction"/u);
  assert.match(component, /className=\{styles\.suggestionRow\}[\s\S]*?<em>Гипотеза ИИ<\/em>/u);
  assert.doesNotMatch(component, /Данные непротиворечивы и достаточны для первичной оценки/u);
  assert.doesNotMatch(component, /Охвачены ключевые области, есть подтверждения и вопросы/u);
});

test("marks missing MRR ARR burn and runway cards as needs-data, not confirmed or calculated", () => {
  assert.match(component, /type MetricCardTone = "green" \| "amber" \| "pink" \| "needs"/u);
  assert.match(component, /if \(tone === "needs"\) return "Нужны данные";/u);

  for (const title of ["MRR — ежемесячная регулярная выручка", "ARR — годовая регулярная выручка", "Темп расходов", "Запас времени"]) {
    assert.match(metricCardSource(title), /tone: "needs"/u);
  }

  assert.doesNotMatch(metricCardSource("MRR — ежемесячная регулярная выручка"), /tone: "green"/u);
  assert.doesNotMatch(metricCardSource("ARR — годовая регулярная выручка"), /tone: "pink"/u);
  assert.doesNotMatch(metricCardSource("Темп расходов"), /tone: "amber"/u);
  assert.doesNotMatch(metricCardSource("Запас времени"), /tone: "pink"/u);
  assert.match(css, /\.metricStatus_needs/u);
});

test("binds 05 metric cards to analytics provenance and report contradiction cards", () => {
  assert.match(
    component,
    /metricCards\(\s*metricDashboard\.cards,\s*metricDashboard\.contradictions,\s*scenarioMetricCards\(workspace\?\.selectedScenario \?\? null\),\s*\)/u,
  );
  assert.match(component, /if \(provenance === "source_fact"\) return "green";/u);
  assert.match(component, /if \(provenance === "calculated"\) return "pink";/u);
  assert.match(component, /status: confirmed\.provenance/u);
  assert.match(component, /if \(status === "contradiction"\) return "Есть расхождение";/u);
  assert.match(component, /function contradictionMetricCard/u);
  assert.match(component, /status === "contradiction"/u);
  assert.match(component, /value: "есть расхождение"/u);
  assert.match(component, /tone: "amber"/u);
  assert.match(component, /metricDashboard\.contradictions/u);
  assert.doesNotMatch(component, /reportMetricCards\[[^\]]*(?:evidence_ref|calculation_ref|contradiction_ref)/u);
});

test("locks 03-05 to the owner-review 1440x1000 density instead of the oversized draft", () => {
  assert.match(css, /\.page\s*\{[\s\S]*?gap:\s*14px;/u);
  assert.match(css, /\.hero h1\s*\{[\s\S]*?font-size:\s*clamp\(28px,\s*2\.15vw,\s*38px\)/u);
  assert.match(css, /\.hero p\s*\{[\s\S]*?font-size:\s*15px;/u);

  assert.match(css, /\.progressRail\s*\{[\s\S]*?min-height:\s*96px;[\s\S]*?padding:\s*12px 30px;/u);
  assert.match(css, /\.railStep span\s*\{[\s\S]*?inline-size:\s*38px;[\s\S]*?min-block-size:\s*38px;/u);
  assert.match(css, /\.progressLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(500px,\s*0\.92fr\)\s+minmax\(0,\s*1\.08fr\);/u);
  assert.match(css, /\.agentPanel,[\s\S]*?\.financialProblem\s*\{[\s\S]*?padding:\s*20px;/u);
  assert.match(css, /\.agentRow\s*\{[\s\S]*?grid-template-columns:\s*48px\s+minmax\(0,\s*1fr\)\s+116px;[\s\S]*?min-height:\s*68px;/u);
  assert.match(css, /\.gateProfile div\s*\{[\s\S]*?grid-template-columns:\s*150px\s+minmax\(0,\s*1fr\);[\s\S]*?min-height:\s*44px;/u);

  assert.match(css, /\.readinessTop\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.58fr\)\s+minmax\(300px,\s*0\.71fr\)\s+minmax\(300px,\s*0\.71fr\);/u);
  assert.match(css, /\.readinessGauge,\s*\n\.circleMetric\s*\{[\s\S]*?padding:\s*20px;/u);
  assert.match(css, /\.gaugeArc\s*\{[\s\S]*?aspect-ratio:\s*2\s*\/\s*1/u);
  assert.match(css, /\.profileMap\s*\{[\s\S]*?min-height:\s*300px;/u);
  assert.match(css, /\.evidenceItem\s*\{[\s\S]*?min-height:\s*72px;/u);
  assert.match(css, /\.aiSuggestion\s*\{[\s\S]*?box-shadow:\s*0 0 48px rgba\(245, 161, 207, 0\.26\);/u);

  assert.match(css, /\.metricCardsTop\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\);/u);
  assert.match(css, /\.metricCard\s*\{[\s\S]*?min-height:\s*170px;[\s\S]*?padding:\s*18px;/u);
  assert.match(css, /\.metricsGrid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.08fr\)\s+minmax\(430px,\s*0\.92fr\);/u);
  assert.match(css, /\.chartCard\s*\{[\s\S]*?min-height:\s*330px;/u);
  assert.match(css, /\.mrrLineChart\s*\{[\s\S]*?min-height:\s*292px;/u);

  assert.doesNotMatch(css, /@media\s*\([^)]*(?:max-width|390px|844px|mobile)/iu);
  assert.match(component, /Либо, после вашего разрешения, могу найти публичные источники/u);
});
