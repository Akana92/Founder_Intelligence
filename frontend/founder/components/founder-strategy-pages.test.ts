import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("./founder-strategy-pages.tsx", import.meta.url),
  "utf8",
);
const launchPackComponent = readFileSync(
  new URL("./founder-launch-pack.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("./founder-strategy-pages.module.css", import.meta.url),
  "utf8",
);
const shellComponent = readFileSync(
  new URL("./founder-shell.tsx", import.meta.url),
  "utf8",
);
const globalCss = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);

test("uses approved desktop composition helpers without inline label concatenation", () => {
  for (const className of [
    "recommendationFact",
    "recommendationFacts",
    "riskDistribution",
    "riskBarLabels",
    "strategyMilestone",
    "timelineMetric",
    "reportGateHeader",
    "lineageOrigin",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(css, /\.recommendationFact\s*\{[\s\S]*?grid-template-columns:\s*38px\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.riskDistribution\s*\{[\s\S]*?border-left:\s*1px solid var\(--strategy-border\)/u);
  assert.match(css, /\.strategyMilestone\s*\{[\s\S]*?border-top:\s*2px solid var\(--strategy-pink\)/u);
  assert.match(css, /\.timelineMetric\s*\{[\s\S]*?min-height:\s*60px/u);
  assert.match(css, /\.reportGateHeader\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/u);
  assert.match(css, /\.lineageOrigin\s*\{[\s\S]*?border-left:\s*1px solid var\(--strategy-border\)/u);

  assert.doesNotMatch(component, /<p>Риск: \{competitor\.risk\}<\/p>/u);
  assert.doesNotMatch(component, /`Основание: \$\{basis\}`/u);
  assert.doesNotMatch(component, /`План действий: \$\{safeText/u);
  assert.match(component, /<span>Риск<\/span>\s*<strong>\{competitor\.risk\}<\/strong>/u);
  assert.match(component, /<span>\{hypothesis \? "ИИ-гипотеза · требует проверки" : "Основано на отчёте"\}<\/span>\s*\{hypothesis \? null : <small>\{basis\}<\/small>\}/u);
});

test("exports the four approved desktop strategy page ids and integration component", () => {
  for (const page of ["market", "risks", "action_plan", "report_center"]) {
    assert.match(component, new RegExp(`"${page}"`, "u"));
    assert.match(
      component,
      new RegExp(`data-founder-strategy-page=[{"']${page.replaceAll("_", "-")}[}"']`, "u"),
    );
  }

  assert.match(component, /export type FounderStrategyPageId/u);
  assert.match(component, /export type FounderStrategyPagesProps/u);
  assert.match(component, /export function FounderStrategyPages/u);
});

test("propagates selected scenarios into risks and action plan as scenario-only validation work", () => {
  assert.match(component, /ScenarioProjectionResponse/u);
  assert.match(component, /StartupScenarioMetric/u);
  assert.match(component, /StartupScenarioVariant/u);
  assert.match(component, /scenarios\?:\s*ScenarioProjectionResponse \| null/u);
  assert.match(component, /selectedScenario\?:\s*StartupScenarioVariant \| null/u);
  assert.match(component, /function scenarioRiskIssues/u);
  assert.match(component, /function ScenarioOnlyDisclosure/u);
  assert.match(component, /workspace\?\.selectedScenario/u);
  assert.match(component, /selectedScenario\.metrics/u);
  assert.match(component, /presentScenarioMetric/u);
  assert.match(component, /presentation:\s*FounderScenarioMetricPresentation/u);
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
  assert.doesNotMatch(component, /не является source_fact/u);
  assert.match(component, /RisksPage[\s\S]*scenarioRiskIssues\(workspace\?\.selectedScenario/u);
  assert.match(component, /ActionPlanPage[\s\S]*scenarioRiskIssues\(workspace\?\.selectedScenario/u);
  assert.doesNotMatch(component, /provenance:\s*"source_fact"/u);
});

test("renders scenario-only metrics as readable cards with semantic disclosure lists", () => {
  for (const className of [
    "scenarioOnlyDisclosure",
    "scenarioDisclosureBody",
    "scenarioIssueGrid",
    "scenarioIssue",
    "scenarioIssueHeader",
    "scenarioDisclosureList",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(
    css,
    /\.scenarioIssueGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(100%,\s*320px\),\s*1fr\)\)/u,
  );
  assert.match(
    css,
    /\.scenarioIssueHeader\s*\{[\s\S]*?display:\s*grid;[\s\S]*?gap:\s*4px;[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/u,
  );
  assert.match(css, /\.scenarioIssueHeader > span\s*\{[\s\S]*?text-align:\s*left/u);
  assert.match(css, /\.scenarioDisclosureList\s*\{[\s\S]*?display:\s*grid;[\s\S]*?gap:\s*4px/u);
  assert.match(component, /<ul className=\{styles\.scenarioDisclosureList\}>[\s\S]*?<li/u);
});

test("renders a real launch pack preview with disabled reasons instead of inert asset CTAs", () => {
  assert.match(component, /import \{ FounderLaunchPack \} from "\.\/founder-launch-pack"/u);
  assert.match(component, /LaunchPackMetadataResponse/u);
  assert.match(component, /launchPack\?:\s*LaunchPackMetadataResponse \| null/u);
  assert.match(component, /<FounderLaunchPack[\s\S]*launchPack=\{workspace\?\.launchPack\}/u);
  assert.match(component, /onRegenerate=\{onBuildWorkpack\}/u);
  assert.match(component, /onClick=\{\(\) => onPrepareAiAsset\?\.\(asset\)\}/u);
  assert.match(component, /Сначала примите рекомендацию выше и дождитесь готового отчёта/u);
  assert.match(component, /Сначала соберите рабочий пакет/u);
  assert.match(component, /aria-describedby=\{!onBuildWorkpack \? "launch-pack-disabled-reason" : undefined\}/u);
  assert.match(component, /id="launch-pack-disabled-reason"/u);
  assert.match(component, /После этого я соберу финальный рабочий пакет/u);
  assert.match(launchPackComponent, /download=\{assetDownloadName\(launchPack,\s*"md"\)\}/u);
  assert.match(launchPackComponent, /download=\{assetDownloadName\(launchPack,\s*"provenance\.md"\)\}/u);
  assert.match(launchPackComponent, /download=\{assetDownloadName\(launchPack,\s*"csv"\)\}/u);
  assert.match(css, /\.markdownPreview\s*\{/u);
  assert.doesNotMatch(component, /disabled=\{!onPrepareAiAsset\}[\s\S]*>Скоро/u);
});

test("keeps launch-pack preview and filenames founder-safe when backend markdown contains internal text", () => {
  const unsafeGeneratedMarkdown = [
    "asset_id: 33333333-3333-4333-8333-333333333333",
    "missing:churn",
    "provenance: source_fact",
    "dependency_refs: mrr_growth_rate",
    "## Executive summary",
    "This launch pack validates the founder statement.",
  ].join("\n");

  for (const rawToken of [
    "33333333-3333-4333-8333-333333333333",
    "missing:churn",
    "source_fact",
    "mrr_growth_rate",
    "Executive summary",
    "This launch pack validates the founder statement.",
  ]) {
    assert.ok(unsafeGeneratedMarkdown.includes(rawToken), `fixture must include unsafe token: ${rawToken}`);
  }

  for (const safeCopy of [
    "Что это за материал",
    "Как использовать черновик",
    "Что скачать",
    "скачиваемом Markdown",
    "не являющегося доказательством",
  ]) {
    assert.match(launchPackComponent, new RegExp(safeCopy, "u"));
  }

  assert.match(launchPackComponent, /function launchPackPreviewSections\(/u);
  assert.match(launchPackComponent, /launchPackPreviewSections\(launchPack\)\.map/u);
  assert.doesNotMatch(launchPackComponent, /previewMarkdown\(launchPack\.body_markdown\)/u);
  assert.doesNotMatch(launchPackComponent, /launchPack\.asset_id/u);
  assert.doesNotMatch(launchPackComponent, /launchPack\.asset_key\}-r/u);
  assert.match(launchPackComponent, /const assetDownloadSlugs: Readonly<Record<string, string>>/u);
  for (const founderSafeSlug of [
    "go-to-market-pack",
    "interview-script",
    "funnel-template",
  ]) {
    assert.match(launchPackComponent, new RegExp(`${founderSafeSlug}"`, "u"));
  }
  assert.match(
    launchPackComponent,
    /return `\$\{assetDownloadSlug\(launchPack\.asset_key\)\}-r\$\{launchPack\.asset_revision\}\.\$\{extension\}`;/u,
  );
});

test("uses real workspace data projections and keeps raw lineage out of founder pages", () => {
  assert.match(component, /buildStartupGtmPresentation/u);
  assert.match(component, /buildFounderReadinessPresentation/u);
  assert.match(component, /buildFounderReportPresentation/u);
  assert.match(component, /workspace\.gtm/u);
  assert.match(component, /workspace\.profile/u);
  assert.match(component, /workspace\.reportSnapshot/u);
  assert.match(component, /workspace\.report/u);

  assert.doesNotMatch(
    component,
    /snapshotHash|profileHash|metricPackHash|source_hashes|parse_inventory|artifact_hash|locator_hash|trace_ids|prompt_versions|raw excerpt|<code/iu,
  );
  assert.doesNotMatch(component, /\bMISSING\b|sha256:/iu);
});

test("renders founder-safe Russian copy and actionable fallback states", () => {
  for (const text of [
    "Рынок и конкуренты",
    "Риски и вопросы",
    "План улучшений",
    "Центр отчёта",
    "Добавить данные",
    "Добавить в план действий",
    "Финальная проверка и решение",
    "Принять рекомендацию",
    "Изменить допущения",
    "Сформировать отчёт",
    "Отчёт зафиксирован",
    "PDF готов",
    "Компания и источник сравнения",
    "Добавьте описание целевого сегмента (ICP), роль покупателя и частоту боли.",
  ]) {
    assert.ok(component.includes(text), `Expected founder-facing copy: ${text}`);
  }

  assert.doesNotMatch(component, /Алексей|FlowPilot|Process Street|Monday\.com|Notion \+ таблицы|68 \/ 100/u);
});

test("keeps visible strategy and lineage copy Russian instead of mixed producer terminology", () => {
  for (const copy of [
    "темп расходов и остаток денег",
    "запас времени и сценарии",
    "Очищенный поиск по открытым источникам и данные кейса разделены",
    "Текущая оценка",
    "исходные документы скрыты",
    "системных инструкций и персональных данных",
  ]) {
    assert.match(component, new RegExp(copy, "u"));
  }

  assert.doesNotMatch(
    component,
    /burn|cash balance|Live inference|live web research|live-поиск|raw документы|prompts|PII|уточню runway|проверю runway|Финансы и runway|данные по runway/u,
  );
});

test("does not fabricate founder-facing metrics or confirmed outcomes", () => {
  assert.doesNotMatch(
    component,
    /5 \+ gtm\.findingCount|\/ 10\b|readiness \|\| "\?"/u,
  );
  assert.doesNotMatch(component, /68 \/ 100|85 \/ 100|готовность отчёта"\s*:\s*\d+/u);
  assert.doesNotMatch(
    component,
    /операционные команды|5 сравнительных пилотов|Снижены|Вероятность: проверить|Влияние: высокое/u,
  );
  assert.doesNotMatch(
    component,
    /Короче цикл сделки|Выше готовность платить|Эффект: \{effect\}|Усилия: \{effort\}/u,
  );
  assert.match(component, /ИИ-гипотеза/u);
  assert.match(component, /Добавьте .*— я/u);
  assert.match(component, /после подтверждения|после оценки команды|после ответа основателя/u);
});

test("keeps generated action-plan and launch-pack product copy readable in Russian", () => {
  for (const copy of [
    "Проверить цену",
    "Проверить время до первой ценности",
    "Гипотеза ИИ",
    "Обсудить стратегию с ИИ",
    "Рабочий пакет ещё не собран",
    "черновик, не являющийся доказательством",
    "происхождение данных",
    "журнал доказательств",
  ]) {
    assert.match(`${component}\n${launchPackComponent}`, new RegExp(copy, "u"));
  }

  assert.doesNotMatch(
    `${component}\n${launchPackComponent}`,
    /Проверить pricing|Проверить time-to-value|Гипотеза AI|Обсудить стратегию с AI|Launch pack ещё не собран|non-evidence draft|Evidence Ledger|Draft launch pack|Provenance appendix|validation plan|Markdown preview\/download/u,
  );
  assert.doesNotMatch(launchPackComponent, />\s*Regenerate\s*</u);
});

test("does not synthesize market competitors or diligence questions without backend rows", () => {
  assert.match(component, /const hasCompetitorRows = competitors\.length > 0/u);
  assert.match(component, /hasCompetitorRows \? \(/u);
  assert.match(component, /const emptyCompetitorPlaceholders = \[/u);
  assert.match(component, /emptyCompetitorPlaceholders\.map\(\(placeholder\) =>/u);
  assert.match(component, /Прямые альтернативы/u);
  assert.match(component, /Косвенные заменители/u);
  assert.match(component, /Ручной обходной путь/u);
  assert.match(component, /Ничего не делать/u);
  assert.match(
    component,
    /Пока нет подтверждённого списка компаний/u,
  );
  assert.doesNotMatch(
    component,
    /\["Прямая альтернатива", "Прямой"[\s\S]*\["Не менять процесс", "Ничего не делать"/u,
  );

  assert.match(component, /const hasDiligenceQuestions = visibleQuestions\.length > 0/u);
  assert.match(component, /const structuredQuestion =\s*workspace\?\.copilotState\?\.question_descriptor\?\.question/u);
  assert.match(component, /: questions\.slice\(0, 3\)/u);
  assert.match(component, /const emptyQuestionUnlocks = \[/u);
  assert.match(component, /После анализа я выберу один вопрос, который сильнее всего изменит вывод/u);
  assert.doesNotMatch(
    component,
    /Какая доля пилотов продлевает подписку через 3 месяца\?|Кто в компании клиента утверждает бюджет\?|Сколько времени и денег занимает запуск одного клиента\?/u,
  );
});

test("keeps public competitor benchmarks visibly separate from confirmed company facts", () => {
  assert.ok(
    component.includes("const isPublicBenchmark = /Публичный ориентир|Публичная гипотеза/u.test("),
  );
  assert.match(
    component,
    /summary:\s*isPublicBenchmark\s*\?\s*"Внешний ориентир из открытого источника; не факт компании\."/u,
  );
  assert.match(
    component,
    /risk:\s*isPublicBenchmark\s*\?\s*"Публичная гипотеза"/u,
  );
  assert.doesNotMatch(
    component,
    /<span className=\{styles\.competitorSummary\}>Подтверждённая альтернатива из данных кейса\.<\/span>/u,
  );
});

test("screen 06 keeps market density honest with source unlocks instead of fake market values", () => {
  assert.match(component, /const marketOpportunitySlots = \[/u);
  assert.match(component, /const marketDimensionUnlocks = \[/u);
  assert.match(component, /const marketSignalIcons = \[UsersRound, Globe2, Target\] as const/u);
  assert.match(component, /const marketRings = marketOpportunitySlots\.map/u);
  assert.match(component, /marketSection\?\.rows\[index\]\?\.\[1\]/u);
  assert.match(component, /className=\{styles\.opportunityBubbles\}/u);
  assert.match(component, /className=\{styles\.signalScoreCard\}/u);
  assert.match(component, /className=\{styles\.signalOpportunity\}/u);
  assert.match(component, /styles\.competitorRiskLine/u);
  assert.match(component, /styles\.marketSourceLegend/u);
  assert.match(component, /<Info aria-hidden="true" size=\{16\} \/>/u);
  assert.match(component, /const visibleMarketSignals = gtm\?\.dimensions\.slice\(0, 3\) \?\? marketDimensionUnlocks/u);
  assert.match(component, /const competitorGuidanceSlots = hasCompetitorRows && competitors\.length < 4/u);
  assert.match(component, /emptyCompetitorPlaceholders\.slice\(competitors\.length\)/u);
  assert.match(component, /className=\{`\$\{styles\.competitorCard\} \$\{styles\.competitorUnlockCard\}`\}/u);
  assert.match(component, /Что добавить/u);
  assert.match(component, /Нужен проверяемый источник/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s*\{[\s\S]*?grid-template-rows:\s*none[\s\S]*?min-height:\s*calc\(100vh - 60px\)/u);
  assert.doesNotMatch(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s*\{[\s\S]*?grid-template-rows:\s*auto 340px 282px 132px auto/u,
  );
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.opportunityLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(270px,\s*1\.02fr\)\s+minmax\(0,\s*0\.78fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.signalPanel\s*\{[\s\S]*?grid-template-rows:\s*auto minmax\(108px,\s*1fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.opportunityBubbles\s*\{[\s\S]*?height:\s*276px[\s\S]*?width:\s*270px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.opportunityBubble\s*\{[\s\S]*?border-radius:\s*50%/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.signalScoreCard\s*\{[\s\S]*?min-width:\s*124px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard\s*\{[\s\S]*?align-items:\s*center[\s\S]*?grid-template-columns:\s*42px minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard\s*\{[\s\S]*?overflow:\s*hidden/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard span\s*\{[\s\S]*?-webkit-line-clamp:\s*3[\s\S]*?overflow:\s*hidden/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard \.statusIcon\s*\{[\s\S]*?width:\s*42px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.competitorGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.competitorCard\s*\{[\s\S]*?grid-template-rows:\s*none[\s\S]*?min-height:\s*0[\s\S]*?overflow:\s*visible/u,
  );
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.competitorUnlockCard\s*\{[\s\S]*?border-style:\s*dashed/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.marketSourceLegend\s*\{[\s\S]*?grid-template-columns:\s*auto auto auto 1px 16px minmax\(0,\s*1fr\)[\s\S]*?min-height:\s*38px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.marketSourceLegend span\s*\{[\s\S]*?text-transform:\s*none/u);

  assert.doesNotMatch(component, /\$4,8 млрд|\$620 млн|\$12 млн|7,2 \/ 10|Привлекательность рынка/u);
});

test("screen 06 owner correction restores mockup hierarchy and stable icon alignment", () => {
  assert.match(component, /className=\{styles\.marketDimensionIcon\}/u);
  assert.match(component, /className=\{styles\.signalNarrative\}/u);
  assert.match(component, /className=\{styles\.signalProofHint\}/u);
  assert.match(component, /className=\{styles\.competitorSummary\}/u);
  assert.match(component, /styles\.competitorCue/u);
  assert.match(component, /className=\{styles\.competitorFootnote\}/u);
  assert.match(component, /className=\{styles\.recommendationLead\}/u);
  assert.match(component, /<article className=\{styles\.miniCard\} data-tone=\{tone\}>/u);
  assert.match(component, /<div className=\{styles\.miniCardCopy\}>\s*<strong>\{title\}<\/strong>\s*<span>\{value\}<\/span>\s*<\/div>/u);
  assert.match(component, /Что подтвердить/u);
  assert.match(component, /Уточните целевой сегмент \(ICP\), повторяемость боли и доступный бюджет/u);
  assert.match(component, /Нужна гипотеза и метрика/u);
  assert.doesNotMatch(component, /<span>Следующий шаг<\/span>/u);

  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s*\{[\s\S]*?grid-template-rows:\s*none/u,
  );

  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.marketSignalList\s+\.factRow\s*\{[\s\S]*?grid-template-columns:\s*38px minmax\(0,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.marketDimensionIcon\s*\{[\s\S]*?background:\s*transparent[\s\S]*?border:\s*0[\s\S]*?height:\s*32px[\s\S]*?width:\s*32px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.signalPanel\s*\{[\s\S]*?grid-template-rows:\s*auto minmax\(108px,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.competitorCard\s*\{[\s\S]*?grid-template-rows:\s*none[\s\S]*?padding:\s*14px 16px/u,
  );
  assert.match(component, /className=\{styles\.recommendationFacts\}/u);
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendationFacts\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.competitorCue\s*\{[\s\S]*?grid-template-columns:\s*22px minmax\(0,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendation\s*\{[\s\S]*?grid-template-rows:\s*auto auto[\s\S]*?min-height:\s*0[\s\S]*?padding:\s*16px 18px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.eyebrow\s*\{[\s\S]*?font-weight:\s*650/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.competitorFootnote\s*\{[\s\S]*?font-size:\s*11\.5px[\s\S]*?line-height:\s*1\.35/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard\[data-tone="green"\]\s+strong\s*\{[\s\S]*?color:\s*var\(--strategy-green\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendation\s+\.pinkButton:disabled\s*\{[\s\S]*?opacity:\s*0\.72/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.miniCardCopy\s*\{[\s\S]*?align-content:\s*center[\s\S]*?min-width:\s*0/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendationFact\s*\{[\s\S]*?align-self:\s*stretch[\s\S]*?position:\s*relative/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendationFact \.statusIcon\s*\{[\s\S]*?left:\s*13px[\s\S]*?position:\s*absolute[\s\S]*?top:\s*50%[\s\S]*?transform:\s*translateY\(-50%\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.miniCard \.statusIcon\s*\{[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="market"\]\s+\.recommendationFact \.statusIcon\s*\{[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
  );
});

test("screen 07 matches the approved risk workspace hierarchy without inventing evidence", () => {
  assert.match(component, /const emptyQuestionUnlocks = \[/u);
  assert.match(component, /className=\{`\$\{styles\.panel\} \$\{styles\.riskSummary\}`\}/u);
  assert.match(component, /className=\{styles\.riskMetricIcon\}/u);
  assert.match(component, /className=\{styles\.riskCopy\}/u);
  assert.match(component, /className=\{styles\.riskAssessment\}/u);
  assert.match(component, /className=\{styles\.riskEvidence\}/u);
  assert.match(component, /className=\{styles\.contradictionNote\}/u);
  assert.match(component, /className=\{styles\.questionFooter\}/u);
  assert.match(component, /className=\{styles\.researchActions\}/u);
  assert.match(component, /Нет источников/u);
  assert.doesNotMatch(component, /Runway меньше 8 месяцев|ARR = \$220 800|оплаченные счета дают \$184 000/u);

  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s*\{[\s\S]*?grid-template-rows:\s*none[\s\S]*?min-height:\s*calc\(100vh - 64px\)/u,
  );
  assert.doesNotMatch(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s*\{[\s\S]*?grid-template-rows:\s*auto 104px minmax\(0,\s*1fr\) 116px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskSummary\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(112px,\s*0\.62fr\)\)\s+minmax\(360px,\s*1\.7fr\)[\s\S]*?padding:\s*14px 18px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskItem\s*\{[\s\S]*?grid-template-columns:\s*40px minmax\(0,\s*1fr\) 94px 86px 92px[\s\S]*?min-height:\s*108px/u,
  );
  assert.match(css, /\.page\[data-founder-strategy-page="risks"\]\s+\.riskLayout\s*\{[\s\S]*?min-height:\s*588px/u);
  assert.doesNotMatch(css, /\.page\[data-founder-strategy-page="risks"\]\s+\.riskLayout\s*\{[\s\S]*?\r?\n\s*height:\s*588px/u);
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.stack\s*\{[\s\S]*?grid-template-rows:\s*232px minmax\(0,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.researchCta\s*\{[\s\S]*?grid-template-columns:\s*54px minmax\(0,\s*1fr\) minmax\(360px,\s*0\.72fr\)[\s\S]*?min-height:\s*116px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.statusIcon\s*\{[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskMetric:nth-child\(4\) strong\s*\{[\s\S]*?font-size:\s*16px[\s\S]*?max-width:\s*96px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskBarEmpty\s*\{[\s\S]*?background:\s*linear-gradient/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.questionRow\s+\.outlineButton\s*\{[\s\S]*?display:\s*grid[\s\S]*?place-items:\s*center/u,
  );
});

test("screen 07 labels unavailable risk scores explicitly and centers every assessment lane", () => {
  assert.match(component, /function RiskScale/u);
  assert.match(component, /Array\.from\(\{ length: 5 \}/u);
  assert.match(component, /data-risk-scale=\{kind\}/u);
  assert.match(
    component,
    /<RiskScale[\s\S]*?kind="probability"[\s\S]*?label="Вероятность"[\s\S]*?score=\{null\}[\s\S]*?valueLabel="Не оценено"/u,
  );
  assert.match(
    component,
    /<RiskScale[\s\S]*?kind="impact"[\s\S]*?label="Влияние"[\s\S]*?score=\{null\}[\s\S]*?valueLabel="Не оценено"/u,
  );
  assert.match(
    component,
    /Баллы вероятности и влияния не выдумываются: они появятся после отдельной\s+подтверждённой оценки риска/u,
  );
  assert.match(component, /className=\{styles\.riskEvidenceGlyph\}/u);
  assert.doesNotMatch(component, /<StatusIcon tone="amber"><AlertTriangle aria-hidden="true" size=\{16\} \/><\/StatusIcon>/u);
  assert.doesNotMatch(component, /<StatusIcon tone="pink"><ShieldAlert aria-hidden="true" size=\{16\} \/><\/StatusIcon>/u);
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskAssessment,[\s\S]*?justify-items:\s*center[\s\S]*?text-align:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskDotScale\s*\{[\s\S]*?display:\s*grid[\s\S]*?grid-template-columns:\s*repeat\(5,\s*10px\)[\s\S]*?justify-content:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskEvidenceGlyph\s*\{[\s\S]*?display:\s*grid[\s\S]*?place-items:\s*center/u,
  );
});

test("screen 07 keeps each risk rank numeral centered inside its circular badge", () => {
  assert.match(
    css,
    /\.riskItem span,[\s\S]*?display:\s*block/u,
    "the regression fixture must include the generic risk span rule that previously overrode the badge layout",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskItem\s*\{[\s\S]*?grid-template-columns:\s*40px\s+minmax\(0,\s*1fr\)/u,
    "risk rows must reserve a stable leading column wide enough that the circular rank badge is not clipped",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.riskItem\s+\.numberBadge\s*\{[\s\S]*?box-sizing:\s*border-box[\s\S]*?display:\s*grid[\s\S]*?height:\s*34px[\s\S]*?justify-self:\s*center[\s\S]*?line-height:\s*1[\s\S]*?margin:\s*0[\s\S]*?place-items:\s*center[\s\S]*?text-align:\s*center[\s\S]*?width:\s*34px/u,
    "the screen-scoped badge rule must win the cascade, avoid inherited inline-flex alignment, and center the numeral on both axes",
  );
});

test("screen 07 keeps each question rank numeral centered inside its circular badge", () => {
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="risks"\]\s+\.questionRow\s+\.numberBadge\s*\{[\s\S]*?box-sizing:\s*border-box[\s\S]*?display:\s*grid[\s\S]*?height:\s*34px[\s\S]*?justify-self:\s*center[\s\S]*?line-height:\s*1[\s\S]*?margin:\s*0[\s\S]*?place-items:\s*center[\s\S]*?text-align:\s*center[\s\S]*?width:\s*34px/u,
    "the screen-scoped question badge rule must win the generic question span cascade",
  );
});

test("matches the approved strategy-screen visual system through scoped css modules", () => {
  for (const selector of [
    ".page",
    ".hero",
    ".marketGrid",
    ".riskSummary",
    ".priorityGrid",
    ".timeline",
    ".reportPreview",
    ".pinkButton",
    ".sourceLegend",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }

  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.competitorGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.priorityGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.riskSummary\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(120px,\s*auto\)\)\s+minmax\(260px,\s*1fr\)/u);
  assert.match(css, /\.hero h1\s*\{[\s\S]*?font-size:\s*28px/u);
  assert.match(css, /\.statusIcon\s*\{[\s\S]*?width:\s*34px/u);
  assert.match(css, /border:\s*1px solid var\(--strategy-border\)/u);
  assert.match(css, /background:\s*linear-gradient/u);
  assert.doesNotMatch(css, /font-size:\s*clamp\(32px,\s*4vw,\s*62px\)|min-height:\s*46px|width:\s*100vw|height:\s*100vh/u);
});

test("locks screens 06-09 to the approved desktop mockup-specific compositions", () => {
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.opportunityBubbles\s*\{[\s\S]*?height:\s*276px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.bubbleLarge\s*\{[\s\S]*?height:\s*262px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="market"\]\s+\.recommendation\s*\{[\s\S]*?min-height:\s*0/u);

  assert.match(css, /\.page\[data-founder-strategy-page="risks"\]\s+\.riskSummary\s*\{[\s\S]*?min-height:\s*104px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="risks"\]\s+\.riskLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(420px,\s*0\.94fr\)/u);

  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s*\{[\s\S]*?gap:\s*6px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.strategyHero\s*\{[\s\S]*?min-height:\s*116px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityCard\s*\{[\s\S]*?min-height:\s*190px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.actionLayout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.08fr\)\s+minmax\(420px,\s*0\.82fr\)/u);

  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportGrid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(520px,\s*1\.04fr\)\s+minmax\(430px,\s*0\.96fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportCover\s*\{[\s\S]*?min-height:\s*470px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.lineagePanel\s*\{[\s\S]*?min-height:\s*164px/u);
});

test("keeps screens 08 and 09 within the owner 1440x1000 density without faux report art", () => {
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s*\{[\s\S]*?gap:\s*6px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.strategyHero\s*\{[\s\S]*?min-height:\s*116px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityCard\s*\{[\s\S]*?min-height:\s*190px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.timelineStep\s*\{[\s\S]*?min-height:\s*150px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.timelineMetric\s*\{[\s\S]*?min-height:\s*48px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.nextAction\s*\{[\s\S]*?min-height:\s*40px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.actionLegend\s*\{[\s\S]*?min-height:\s*60px/u);

  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportCover\s*\{[\s\S]*?min-height:\s*470px/u);
  assert.doesNotMatch(css, /\.reportCover\s*\{[\s\S]*?radial-gradient\(circle at 78% 34%/u);
});

test("screen 09 matches the approved report-center hierarchy and centers every circular icon", () => {
  for (const className of [
    "reportVersionPill",
    "reportMark",
    "reportContents",
    "reportContentsLabel",
    "reportGateBody",
    "reportGateVisual",
    "formatIcon",
    "formatDescription",
    "formatStatus",
    "lineageLead",
    "lineageFact",
    "lineageOriginHeader",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(component, /src=\{founderIntelligenceMark\}/u);
  assert.match(component, /workspace\?\.report\?\.snapshotLabel/u);
  assert.match(component, /description="Для презентации и отправки"/u);
  assert.match(component, /description="Интерактивный просмотр"/u);
  assert.match(component, /description="Структурированные данные"/u);
  assert.match(component, /const reportNavigationLabels/u);
  assert.match(component, /reportNavigationLabels\[section\.key\] \?\? section\.title/u);
  assert.match(component, /className=\{styles\.reportContentsLabel\}>Содержание отчёта/u);
  assert.ok(
    component.indexOf("styles.reportContents") < component.indexOf("styles.reportPager"),
    "report contents must precede the page controls like the approved mockup",
  );

  assert.match(
    css,
    /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportPager\s*\{[\s\S]*?display:\s*grid[\s\S]*?grid-template-columns:\s*minmax\(140px,\s*1fr\)\s+auto\s+minmax\(140px,\s*1fr\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportGateBody\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+148px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportContents\s*\{[\s\S]*?border-top:\s*1px solid rgba\(255,\s*255,\s*255,\s*0\.08\)/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="report-center"\]\s+:is\(\.reportConclusion \.statusIcon,\s*\.reportGateVisual \.statusIcon,\s*\.lineagePanel > \.statusIcon,\s*\.formatIcon\)\s*\{[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="report-center"\]\s+:is\(\.reportConclusion \.statusIcon,\s*\.reportGateVisual \.statusIcon,\s*\.lineagePanel > \.statusIcon,\s*\.formatIcon\) > svg\s*\{[\s\S]*?display:\s*block[\s\S]*?margin:\s*0/u,
  );
});

test("keeps zero-contradiction risks neutral and prevents severity distribution when counts are zero", () => {
  assert.match(component, /const hasContradictions = contradictionCount > 0/u);
  assert.match(component, /const emptyRiskPlaceholders = \[/u);
  assert.match(component, /emptyRiskPlaceholders\.map\(\(risk\) =>/u);
  assert.match(component, /Финансовая модель/u);
  assert.match(component, /Канал продаж/u);
  assert.match(component, /Удержание и ценность/u);
  assert.match(component, /const visibleQuestions =/u);
  assert.match(component, /\["Вопросов", visibleQuestions\.length, "blue"\]/u);
  assert.match(component, /hasContradictions \? "Найдено важное противоречие" : "Противоречий не выявлено"/u);
  assert.match(component, /hasContradictions[\s\S]*Разобрать противоречие[\s\S]*Добавить данные для проверки/u);
  assert.match(component, /className=\{`\$\{styles\.riskBar\} \$\{hasContradictions \? "" : styles\.riskBarEmpty\}`\}/u);
  assert.match(component, /hasContradictions \? \(\s*<>\s*<span \/><span \/><span \/><span \/>\s*<\/>\s*\) : null/u);
  assert.match(css, /\.riskBarEmpty\s*\{[\s\S]*?display:\s*block/u);
  assert.match(css, /\.riskItem strong,\s*\n\.questionRow strong\s*\{[\s\S]*?display:\s*block/u);
  assert.doesNotMatch(component, /Уточнить значение/u);
});

test("routes risk questions only to evidence-compatible actions", () => {
  const risksPage = component.slice(
    component.indexOf("function RisksPage"),
    component.indexOf("function ActionPlanPage"),
  );

  assert.match(component, /CopilotStateResponse/u);
  assert.match(component, /copilotState\?:\s*CopilotStateResponse \| null/u);
  assert.match(risksPage, /const structuredQuestion =\s*workspace\?\.copilotState\?\.question_descriptor\?\.question\?\.trim\(\) \?\?/u);
  assert.match(risksPage, /workspace\?\.copilotState\?\.next_question\?\.trim\(\) \?\?/u);
  assert.match(risksPage, /const visibleQuestions = structuredQuestion\s*\? \[structuredQuestion, \.\.\.questions\.filter/u);
  assert.match(risksPage, /question\.trim\(\) !== structuredQuestion/u);
  assert.match(risksPage, /const isStructuredAnswer = question\.trim\(\) === structuredQuestion/u);
  assert.match(risksPage, /const isPublicResearchQuestion = !isStructuredAnswer && publicResearchQuestionPattern\.test\(question\)/u);
  assert.match(risksPage, /isStructuredAnswer\s*\? "Ответить"\s*:\s*isPublicResearchQuestion\s*\? "Публичный поиск"\s*:\s*"Добавить данные"/u);
  assert.match(risksPage, /isStructuredAnswer\s*\? \(\(\) => answerQuestion\?\.\(question\)\)\s*:\s*isPublicResearchQuestion\s*\? \(\(\) => onRequestResearchConsent\?\.\("question"\)\)\s*:\s*onAddEvidence/u);
  assert.doesNotMatch(risksPage, /index === 2 \? "Добавить данные" : "Ответить"/u);
});

test("risks public research CTA opens an accessible consent dialog instead of a misplaced strip", () => {
  const risksPage = component.slice(
    component.indexOf("function RisksPage"),
    component.indexOf("function ActionPlanPage"),
  );
  const marketPage = component.slice(
    component.indexOf("function MarketPage"),
    component.indexOf("function RisksPage"),
  );
  const topLevelPage = component.slice(
    component.indexOf("export function FounderStrategyPages"),
  );

  for (const className of [
    "researchConsentBackdrop",
    "researchConsentDialog",
    "researchConsentActions",
    "researchConsentError",
    "researchConsentFineprint",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(topLevelPage, /const \[researchConsentSource, setResearchConsentSource\] = useState<[^>]+>\(null\)/u);
  assert.match(topLevelPage, /function openResearchConsent\(source: ResearchConsentSource\)/u);
  assert.match(topLevelPage, /<ResearchConsentDialog[\s\S]*?onConfirm=\{confirmResearchConsent\}/u);
  assert.match(marketPage, /onClick=\{\(\) => onRequestResearchConsent\?\.\("market"\)\}[\s\S]*Обновить исследование/u);
  assert.match(risksPage, /onClick=\{\(\) => onRequestResearchConsent\?\.\("risks"\)\}[\s\S]*Разрешить безопасный поиск/u);
  assert.match(risksPage, /isResearch \? \(\(\) => onRequestResearchConsent\?\.\("question"\)\) : onAddEvidence/u);
  assert.match(component, /role="dialog"/u);
  assert.match(component, /aria-modal="true"/u);
  assert.match(component, /aria-labelledby="public-research-consent-title"/u);
  assert.match(component, /aria-describedby="public-research-consent-description"/u);
  assert.match(component, /id="public-research-consent-title"/u);
  assert.match(component, /id="public-research-consent-description"/u);
  assert.match(component, /Отмена/u);
  assert.match(component, /Подтвердить и запустить онлайн/u);
  assert.match(component, /Подтвердить и запустить офлайн-демо/u);
  assert.match(component, /Не удалось запустить публичный поиск/u);
  assert.match(component, /Публичный поиск пока недоступен/u);
  assert.match(component, /disabled=\{Boolean\(busy\) \|\| !onAllowResearch\}/u);
  assert.match(component, /aria-busy=\{Boolean\(busy\)\}/u);
  assert.match(component, /aria-live="polite"/u);
  assert.match(component, /Внешние ориентиры не становятся внутренними фактами/u);
  assert.match(component, /MRR, выручку, расходы, остаток денег и клиентские факты/u);
  assert.match(component, /const accepted = await onAllowResearch\(mode\)/u);
  assert.match(component, /if \(accepted\) \{[\s\S]*?setResearchConsentSource\(null\)/u);
  assert.doesNotMatch(risksPage, /onClick=\{onAllowResearch\}/u);
  assert.doesNotMatch(marketPage, /onClick=\{onAllowResearch\}/u);
  assert.doesNotMatch(risksPage, /onAddEvidence \?\? onAllowResearch|const addQuestionEvidence = onAddEvidence \?\? onAllowResearch/u);

  assert.match(css, /\.researchConsentBackdrop\s*\{[\s\S]*?position:\s*fixed/u);
  assert.match(css, /\.researchConsentBackdrop\s*\{[\s\S]*?inset:\s*0/u);
  assert.match(css, /\.researchConsentBackdrop\s*\{[\s\S]*?overflow-y:\s*auto/u);
  assert.match(css, /\.researchConsentDialog\s*\{[\s\S]*?inline-size:\s*fit-content/u);
  assert.match(css, /\.researchConsentDialog\s*\{[\s\S]*?max-inline-size:\s*min\(100%,\s*64rem\)/u);
  assert.match(css, /\.researchConsentDialog\s*\{[\s\S]*?max-height:\s*min\(45rem,\s*calc\(100vh - 3rem\)\)/u);
  assert.match(css, /@media \(max-width:\s*720px\)[\s\S]*\.researchConsentDialog\s*\{[\s\S]*?inline-size:\s*100%/u);
  assert.match(css, /\.researchConsentBackdrop\s*\{[\s\S]*?z-index:\s*120/u);

  assert.match(shellComponent, /async function requestSafeResearch\(\s*acquisitionMode\?: RequestedResearchAcquisitionMode,\s*\): Promise<boolean>/u);
  assert.match(shellComponent, /action\.action === "prepare_public_research"/u);
  assert.match(shellComponent, /defaultCaseCopilotPublicResearchMode\(publicResearchAction\)/u);
  assert.match(shellComponent, /acquisitionMode: researchAcquisitionMode/u);
  assert.match(shellComponent, /publicResearchAction\.status !== "requires_consent"/u);
  assert.match(shellComponent, /typeof publicResearchAction\.payload\.focus !== "string"/u);
  assert.match(shellComponent, /Number\.isInteger\(publicResearchAction\.payload\.expected_case_revision\)/u);
  assert.match(shellComponent, /return false/u);
  assert.match(shellComponent, /return accepted/u);
  assert.match(globalCss, /\.founder-global-busy\s*\{[\s\S]*?pointer-events:\s*none/u);
});

test("locks strategy mutations immediately and shows readable progress copy", () => {
  const actionPlanPage = component.slice(
    component.indexOf("function ActionPlanPage"),
    component.indexOf("function ReportCenterPage"),
  );
  const reportCenterPage = component.slice(
    component.indexOf("function ReportCenterPage"),
    component.indexOf("export function FounderStrategyPages"),
  );
  const topLevelPage = component.slice(
    component.indexOf("export function FounderStrategyPages"),
  );

  assert.match(
    actionPlanPage,
    /disabled=\{!onPrepareAiAsset \|\| Boolean\(workspace\?\.busy\)\}[\s\S]*?workspace\?\.busy \? "Готовлю…" : "Подготовить"/u,
  );
  assert.match(
    actionPlanPage,
    /disabled=\{!onBuildWorkpack \|\| Boolean\(workspace\?\.busy\)\}[\s\S]*?workspace\?\.busy \? "Собираю рабочий пакет…" : "Собрать рабочий пакет"/u,
  );
  assert.match(
    reportCenterPage,
    /disabled=\{!gateReady \|\| !onFreezeReport \|\| Boolean\(workspace\?\.busy\)\}[\s\S]*?workspace\?\.busy \? "Формирую отчёт…" : "Сформировать отчёт"/u,
  );

  assert.match(
    topLevelPage,
    /const \[researchConsentPending, setResearchConsentPending\] = useState\(false\)/u,
  );
  assert.match(
    topLevelPage,
    /if \(!onAllowResearch \|\| workspace\?\.busy \|\| researchConsentPending\)/u,
  );
  assert.match(
    topLevelPage,
    /setResearchConsentPending\(true\)[\s\S]*?try \{[\s\S]*?finally \{[\s\S]*?setResearchConsentPending\(false\)/u,
  );
  assert.match(
    topLevelPage,
    /busy=\{Boolean\(workspace\?\.busy\) \|\| researchConsentPending\}/u,
  );
});

test("keeps action plan compact and report center reflects approved final report state", () => {
  assert.match(css, /\.priorityCard\s*\{[\s\S]*?min-height:\s*170px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityCard\s*\{[\s\S]*?min-height:\s*190px/u);
  assert.match(css, /\.timelineStep\s*\{[\s\S]*?min-height:\s*84px/u);
  assert.match(css, /\.strategyHero\s*\{[\s\S]*?grid-template-columns:\s*46px\s+minmax\(0,\s*1\.1fr\)\s+minmax\(260px,\s*0\.9fr\)/u);
  assert.match(component, /function reportReadinessScore/u);
  assert.match(component, /Math\.round\(\(earned \/ report\.sections\.length\) \* 100\)/u);
  assert.match(component, /className=\{styles\.readinessLabel\}>Готовность/u);
  assert.match(component, /report \? "\/ 100" : "после анализа"/u);
  assert.doesNotMatch(component, /из \{report\.sections\.length\} подтверждено/u);
  assert.match(component, /freezeApproved = Boolean\(workspace\?\.report\?\.freezeApproved\)/u);
  assert.match(component, /reportStatus = hasApprovedLineage[\s\S]*"Отчёт зафиксирован"/u);
  assert.match(component, /hasApprovedLineage && approvedPdfUrl[\s\S]*Открыть PDF/u);
  assert.match(component, /status=\{approvedPdfUrl \? "PDF готов"/u);
  assert.match(component, /<small>Одобрено<\/small><strong>\{hasApprovedLineage \? "да" : "после подтверждения"\}<\/strong>/u);
  assert.doesNotMatch(component, /Одобрено: ожидает решения/u);
});

test("shell wires every risk recovery action and closes the assistant before page navigation", () => {
  const riskShell = shellComponent.slice(
    shellComponent.indexOf('activeView === "risks"'),
    shellComponent.indexOf('activeView === "action_plan"'),
  );
  const openView = shellComponent.slice(
    shellComponent.indexOf("function openView"),
    shellComponent.indexOf("function openDataRoom"),
  );

  assert.match(riskShell, /onAddEvidence=\{openDataRoom\}/u);
  assert.match(riskShell, /onAnswerQuestion=\{openCaseCopilotForQuestion\}/u);
  assert.match(riskShell, /onDiscussRisk=\{openCaseCopilot\}/u);
  assert.match(riskShell, /onShowEvidence=\{openRiskEvidence\}/u);
  assert.match(openView, /setCaseCopilotOpen\(false\)/u);
  assert.match(shellComponent, /function openCaseCopilotForResearch\(\)/u);
  assert.match(shellComponent, /setCaseCopilotPreferredAnswerType\("public_research"\)/u);
  assert.match(shellComponent, /onOpenResearch=\{openCaseCopilotForResearch\}/u);
});

test("primary-ready report and back-to-analysis navigation return to the Gate 2 decision", () => {
  const resolver = shellComponent.slice(
    shellComponent.indexOf("function resolveSidebarView"),
    shellComponent.indexOf("const activeSidebarView"),
  );
  const backToAnalysis = shellComponent.slice(
    shellComponent.indexOf("function openAnalysisOrDataRoom"),
    shellComponent.indexOf("async function requestSafeResearch"),
  );

  assert.match(resolver, /stage === "primary_ready"[\s\S]*view === "report_center"[\s\S]*return "progress_gate2"/u);
  assert.match(backToAnalysis, /stage === "primary_ready"[\s\S]*openView\("progress_gate2", "Новый анализ"\)/u);
});

test("action plan exposes the final decision checkpoint with exact owner actions", () => {
  const actionPlanPage = component.slice(
    component.indexOf("function ActionPlanPage"),
    component.indexOf("function ReportCenterPage"),
  );
  const actionPlanShell = shellComponent.slice(
    shellComponent.indexOf('activeView === "action_plan"'),
    shellComponent.indexOf('activeView === "report_center"'),
  );

  assert.match(actionPlanPage, /Финальная проверка и решение/u);
  assert.match(actionPlanPage, /onClick=\{onAcceptDirection\}[\s\S]*?>Принять рекомендацию/u);
  assert.match(actionPlanPage, /onClick=\{onSuggestAlternative\}[\s\S]*?>Изменить допущения/u);
  assert.doesNotMatch(actionPlanPage, /Принять направление|Предложить альтернативу/u);
  assert.match(actionPlanShell, /onAcceptDirection=\{[\s\S]*handleGate3Approval/u);
  assert.match(actionPlanShell, /onSuggestAlternative=\{openCaseCopilot\}/u);
});

test("action plan presents the final owner flow as one ordered decision sequence", () => {
  const actionPlanPage = component.slice(
    component.indexOf("function ActionPlanPage"),
    component.indexOf("function ReportCenterPage"),
  );
  const finalDecisionPanel = actionPlanPage.slice(
    actionPlanPage.indexOf("Финальная проверка и решение"),
    actionPlanPage.indexOf("<ScenarioOnlyDisclosure"),
  );

  const acceptIndex = finalDecisionPanel.indexOf("Принять рекомендацию");
  const changeIndex = finalDecisionPanel.indexOf("Изменить допущения");
  const reportIndex = finalDecisionPanel.indexOf("Сформировать отчёт");

  assert.ok(acceptIndex >= 0, "final flow must start with accepting the recommendation");
  assert.ok(changeIndex > acceptIndex, "changing assumptions must immediately follow acceptance");
  assert.ok(reportIndex > changeIndex, "forming the report must be the next visible owner action");
  assert.doesNotMatch(finalDecisionPanel, /Gate\s*\d|Принять направление|Предложить альтернативу/u);
});

test("strategy pages surface one completed online research run across market risks and action plan", () => {
  const marketPage = component.slice(
    component.indexOf("function MarketPage"),
    component.indexOf("function RisksPage"),
  );
  const risksPage = component.slice(
    component.indexOf("function RisksPage"),
    component.indexOf("function ActionPlanPage"),
  );
  const actionPlanPage = component.slice(
    component.indexOf("function ActionPlanPage"),
    component.indexOf("function ReportCenterPage"),
  );

  assert.match(component, /ResearchJobResponse/u);
  assert.match(component, /ScenarioMetricComparison/u);
  assert.match(component, /researchJob\?:\s*ResearchJobResponse \| null/u);
  assert.match(component, /researchMetricComparison\?:\s*ScenarioMetricComparison \| null/u);
  assert.match(component, /function buildResearchImpactSummary/u);
  assert.match(component, /buildCaseCopilotResearchJobPresentation/u);
  assert.match(component, /data-public-research-impact/u);
  assert.match(marketPage, /const researchImpact = buildResearchImpactSummary\(workspace\)/u);
  assert.match(risksPage, /const researchImpact = buildResearchImpactSummary\(workspace\)/u);
  assert.match(actionPlanPage, /const researchImpact = buildResearchImpactSummary\(workspace\)/u);
  assert.match(marketPage, /<PublicResearchImpactPanel impact=\{researchImpact\} variant="market"/u);
  assert.match(risksPage, /<PublicResearchImpactPanel impact=\{researchImpact\} variant="risks"/u);
  assert.match(actionPlanPage, /<PublicResearchImpactPanel impact=\{researchImpact\} variant="action_plan"/u);
  assert.match(component, /Онлайн-исследование обновило этот раздел/u);
  assert.match(component, /Сценарий ИИ, не факт компании/u);
  assert.match(component, /Публичные ориентиры не стали внутренними фактами компании/u);
  assert.match(css, /\.publicResearchImpact\s*\{/u);
  assert.match(css, /\.researchDeltaList\s*\{/u);
});

test("strategy pages show source-only online research with clickable citations and AI scenario labels", () => {
  assert.match(component, /const hasSourceOnlyResearchImpact/u);
  assert.match(component, /job\.citations\.length > 0/u);
  assert.match(component, /job\.changed_blocks\.includes\("market_research"\)/u);
  assert.match(component, /const sourceUrls = presentation\.citations/u);
  assert.match(component, /href=\{source\.url\}/u);
  assert.match(component, /target="_blank"/u);
  assert.match(component, /domain/u);
  assert.match(component, /retrievalDate/u);
  assert.match(component, /До онлайн-ресерча/u);
  assert.match(component, /После онлайн-ресерча/u);
  assert.match(component, /Сценарий ИИ, не факт компании/u);
  assert.doesNotMatch(component, /Рынок, конкуренты и ценовые аналоги обновлены[\s\S]*?если нет источников/u);
});

test("strategy public research source labels use collision-safe React keys", () => {
  assert.doesNotMatch(component, /sourceLabels\.map\(\(label\) => <li key=\{label\}>/u);
  assert.match(component, /sourceLabels\.map\(\(label, index\) => <li key=\{`source-label-\$\{index\}-\$\{label\}`\}>/u);
});

test("strategy consent dialog offers adjacent online and offline launches with combined profile consent copy", () => {
  assert.match(component, /type ResearchConsentMode = "live_public_research" \| "deterministic_offline_fixture"/u);
  assert.match(component, /const researchConsentModes/u);
  assert.match(component, /Онлайн/u);
  assert.match(component, /Офлайн-демо/u);
  assert.match(component, /selectedMode/u);
  assert.match(component, /onModeChange/u);
  assert.match(component, /одним действием запущу выбранный режим/u);
  assert.match(component, /обновлю этот же кейс до свежей версии данных/u);
  assert.match(component, /подтвержу извлеч[её]нный профиль/u);
  assert.match(component, /MRR, выручку, расходы, остаток денег и клиентские факты нужно подтвердить вручную или документом/u);
  assert.match(component, /Проверка стратегии и финальный отчёт останутся отдельными решениями/u);
  assert.match(component, /onConfirm\(selectedMode\)/u);
});

test("strategy consent dialog does not expose Gate or token jargon to the owner", () => {
  const dialogStart = component.indexOf("function ResearchConsentDialog");
  const dialogEnd = component.indexOf("function MarketPage");
  assert.notEqual(dialogStart, -1);
  assert.notEqual(dialogEnd, -1);

  const dialog = component.slice(dialogStart, dialogEnd);
  assert.doesNotMatch(dialog, /Gate\s*\d|токен|token/u);
});

test("report center explains the exact next owner action instead of raw gate numbers", () => {
  assert.match(component, /function reportCenterNextAction/u);
  assert.match(component, /Вернитесь к анализу и завершите профиль проекта/u);
  assert.match(component, /Подождите: система обновляет этот же кейс/u);
  assert.match(component, /Откройте «План действий» и нажмите «Принять рекомендацию»/u);
  assert.match(component, /Проверьте черновик и нажмите «Сформировать отчёт»/u);
  assert.match(component, /PDF, HTML и JSON готовы к скачиванию/u);
  assert.doesNotMatch(component, /Собрать итоговый отчёт/u);
  assert.doesNotMatch(component, /Подтвердить и сформировать PDF|Формирую PDF|Принять направление/u);
  assert.doesNotMatch(component, /Gate 4 · нужно ваше решение/u);
  assert.doesNotMatch(component, /После Gate 4 система покажет/u);
});

test("report center gives every unmet prerequisite a direct owner resolution action", () => {
  const reportCenterPage = component.slice(
    component.indexOf("function ReportCenterPage"),
    component.indexOf("export function FounderStrategyPages"),
  );
  const reportShell = shellComponent.slice(
    shellComponent.indexOf('activeView === "report_center"'),
    shellComponent.indexOf('activeView === "advisor_next_question"'),
  );

  assert.match(component, /onOpenOverview\?: \(\) => void/u);
  assert.match(component, /onOpenActionPlan\?: \(\) => void/u);
  assert.match(reportCenterPage, /const reportBlockers = \[/u);
  assert.match(reportCenterPage, /Профиль ещё не готов/u);
  assert.match(reportCenterPage, /Вернуться к анализу/u);
  assert.match(reportCenterPage, /Нет подтверждённых оснований/u);
  assert.match(reportCenterPage, /Откройте «Обзор» и нажмите «Добавить данные»/u);
  assert.match(reportCenterPage, /Открыть обзор/u);
  assert.match(reportCenterPage, /Рекомендация ещё не принята/u);
  assert.match(reportCenterPage, /В Плане действий нажмите «Принять рекомендацию»/u);
  assert.match(reportCenterPage, /Открыть план действий/u);
  assert.match(reportCenterPage, /report && !gateReady && !hasApprovedLineage/u);
  assert.match(reportCenterPage, /onClick=\{blocker\.onClick\}/u);
  assert.match(reportShell, /onBackToAnalysis=\{openAnalysisOrDataRoom\}/u);
  assert.match(reportShell, /onOpenOverview=\{\(\) => openView\("overview", "Обзор"\)\}/u);
  assert.match(reportShell, /onOpenActionPlan=\{\(\) => openView\("action_plan", "План действий"\)\}/u);
});

test("report center owner-facing component copy has no Gate or token jargon", () => {
  const reportCenterPage = component.slice(
    component.indexOf("function ReportCenterPage"),
    component.indexOf("export function FounderStrategyPages"),
  );

  assert.match(reportCenterPage, /Финальная проверка и решение/u);
  assert.match(reportCenterPage, /Сформировать отчёт/u);
  assert.match(reportCenterPage, /Формирую отчёт…/u);
  assert.match(reportCenterPage, /Нажатие «Сформировать отчёт» зафиксирует эту версию/u);
  assert.match(reportCenterPage, /одна зафиксированная версия создаст PDF, HTML и JSON/u);
  assert.doesNotMatch(reportCenterPage, /Gate\s*\d|токен|token/u);
});

test("labels document statements as stated rather than independently confirmed", () => {
  assert.match(component, /Заявлено в материалах/u);
  assert.match(component, /Указано в ваших документах/u);
  assert.match(component, /Анализ на основе заявлений из документов/u);
  assert.doesNotMatch(
    component,
    /Факт из материалов|Подтверждено вашими документами|Анализ на основе подтверждённых фактов/u,
  );
});

test("screen 08 keeps sparse backend proposals honest without an empty priority panel", () => {
  assert.match(component, /const emptyActionPrioritySlots = \[/u);
  assert.match(component, /const actionItems = actionSection\?\.items\.slice\(0, 4\) \?\? \[\]/u);
  assert.match(component, /const priorityGuidanceSlots = actionItems\.length > 0 && improvements\.length < 4/u);
  assert.match(component, /emptyActionPrioritySlots\.slice\(0, 4 - improvements\.length\)/u);
  assert.match(component, /priorityGuidanceSlots\.map\(\(slot, index\) =>/u);
  assert.match(component, /Что разблокирует следующий приоритет/u);
  assert.match(component, /Добавьте действие, которое уже подтверждено отчётом/u);
  assert.match(component, /className=\{`\$\{styles\.priorityGrid\} \$\{styles\.priorityGridHonest\}`\}/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityGridHonest\s*\{[\s\S]*?grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(178px,\s*1fr\)\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityGapCard\s*\{[\s\S]*?border-style:\s*dashed/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.strategyHero\s*\{[\s\S]*?grid-template-columns:\s*54px\s+minmax\(0,\s*1\.05fr\)\s+minmax\(250px,\s*0\.7fr\)\s+minmax\(250px,\s*0\.66fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.timeline\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(142px,\s*1fr\)\)/u);

  assert.doesNotMatch(component, /Эффект: высокий|Усилия: средние|Вероятность: проверить/u);
});

test("screen 08 preserves the mockup hierarchy with honest priority and timeline states", () => {
  assert.match(component, /className=\{styles\.strategyHeroBenefits\}/u);
  assert.match(component, /className=\{styles\.strategyHeroActions\}/u);
  assert.match(component, /className=\{styles\.priorityHeader\}/u);
  assert.match(component, /className=\{styles\.priorityAssessment\}/u);
  assert.match(component, /ИИ-гипотеза · требует проверки/u);
  assert.match(component, /Эффект<\/span>\s*<strong>После проверки<\/strong>/u);
  assert.match(component, /Усилия<\/span>\s*<strong>После оценки команды<\/strong>/u);
  assert.match(component, /className=\{styles\.timelineMarker\}/u);
  assert.match(component, /className=\{styles\.timelineDay\}/u);
  assert.match(component, /<span>Целевой показатель<\/span>/u);

  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.strategyHero\s*\{[\s\S]*?grid-template-columns:\s*54px\s+minmax\(0,\s*1\.05fr\)\s+minmax\(250px,\s*0\.7fr\)\s+minmax\(250px,\s*0\.66fr\)/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.timeline::before\s*\{[\s\S]*?height:\s*2px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.timelineMarker\s*\{[\s\S]*?place-items:\s*center/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.actionLegend\s*\{[\s\S]*?border:\s*1px solid var\(--strategy-border\)/u);
});

test("screen 08 keeps priority and legend glyphs centered inside their circular slots", () => {
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityHeader \.statusIcon\s*\{[\s\S]*?align-items:\s*center[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
    "priority glyph slots must override generic card span typography and center the SVG on both axes",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="action-plan"\]\s+\.actionLegend \.statusIcon\s*\{[\s\S]*?align-items:\s*center[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
    "legend glyph slots must override the later legend span layout instead of pinning the icon to the top edge",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="action-plan"\]\s+:is\(\.priorityHeader, \.actionLegend\) \.statusIcon > svg\s*\{[\s\S]*?display:\s*block[\s\S]*?margin:\s*0/u,
    "screen 08 SVG glyphs must not inherit inline baseline spacing",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityHeader \.statusIcon > svg\s*\{[\s\S]*?height:\s*20px[\s\S]*?transform:\s*translate\(0\.5px,\s*0\.75px\)[\s\S]*?transform-origin:\s*center[\s\S]*?width:\s*20px/u,
    "priority glyphs need a fixed visual box plus optical correction inside the circle",
  );
  assert.match(
    css,
    /\.page\[data-founder-strategy-page="action-plan"\]\s+\.actionLegend \.statusIcon > svg\s*\{[\s\S]*?height:\s*18px[\s\S]*?transform:\s*translate\(0\.5px,\s*0\.75px\)[\s\S]*?transform-origin:\s*center[\s\S]*?width:\s*18px/u,
    "legend glyphs need the same optical centering contract for future screen work",
  );
});

test("report center exposes same-case PDF, HTML, and JSON links after final freeze", () => {
  assert.match(component, /const allReportUrlsPresent = Boolean\(pdfUrl && htmlUrl && jsonUrl\)/u);
  assert.match(component, /const hasApprovedLineage = Boolean\(freezeApproved && allReportUrlsPresent\)/u);
  assert.match(component, /const approvedPdfUrl = hasApprovedLineage \? pdfUrl : undefined/u);
  assert.match(component, /const approvedHtmlUrl = hasApprovedLineage \? htmlUrl : undefined/u);
  assert.match(component, /const approvedJsonUrl = hasApprovedLineage \? jsonUrl : undefined/u);
  assert.match(component, /href=\{approvedPdfUrl\}/u);
  assert.match(component, /href=\{approvedHtmlUrl\}/u);
  assert.match(component, /href=\{approvedJsonUrl\}/u);
  assert.match(component, /className=\{`\$\{styles\.formatCard\} \$\{styles\.formatCardLink\}`\}/u);
  assert.match(component, /aria-label="Разделы отчёта"/u);
  assert.match(component, /report\.sections\.slice\(0, 6\)\.map/u);
  assert.match(component, /const nextPage = index \+ 1/u);
  assert.match(component, /setReportPage\(nextPage\)/u);
  assert.match(component, /if \(nextPage !== visibleReportPage\)/u);
  assert.match(css, /\.formatCardLink::after\s*\{[\s\S]*?content:\s*"Открыть"/u);
  assert.match(css, /\.reportTabs\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.reportTabs button\[aria-current="page"\]/u);
});

test("report center keeps approved lineage copy pending until final approval and all export urls exist", () => {
  assert.match(component, /reportStatus = hasApprovedLineage[\s\S]*"Отчёт зафиксирован"/u);
  assert.match(component, /hasApprovedLineage && approvedPdfUrl[\s\S]*Открыть PDF/u);
  assert.match(component, /status=\{approvedPdfUrl \? "PDF готов" : gateReady \? "После подтверждения" : "После анализа"\}/u);
  assert.match(component, /status=\{approvedHtmlUrl \? "HTML готов" : gateReady \? "После подтверждения" : "После анализа"\}/u);
  assert.match(component, /status=\{approvedJsonUrl \? "JSON готов" : gateReady \? "После подтверждения" : "После анализа"\}/u);
  assert.match(component, /hasApprovedLineage \? "Одна зафиксированная версия — три формата" : "Одна зафиксированная версия создаст три формата"/u);
  assert.match(component, /hasApprovedLineage\s*\?\s*"PDF, HTML и JSON созданы из одной зафиксированной версии проекта и не расходятся по данным\."\s*:\s*"После финального решения одна зафиксированная версия создаст PDF, HTML и JSON для этого же кейса\."/u);
  assert.match(component, /<small>Одобрено<\/small><strong>\{hasApprovedLineage \? "да" : "после подтверждения"\}<\/strong>/u);
  assert.doesNotMatch(component, /Одобрено: \{freezeApproved \? "да" : "ожидает решения"\}/u);
});

test("report center uses the real planet asset through Next Image with DOM overlay text", () => {
  assert.match(component, /import Image from "next\/image"/u);
  assert.match(component, /<Image\s+alt=""/u);
  assert.match(component, /className=\{styles\.reportCoverImage\}/u);
  assert.match(component, /fill/u);
  assert.match(component, /sizes="\(min-width: 1200px\) 44vw, 100vw"/u);
  assert.match(component, /src="\/report-cover-planet\.png"/u);
  assert.match(component, /<div className=\{styles\.reportCoverOverlay\}>[\s\S]*?<h2>\{projectName\(workspace\)\}<\/h2>/u);
  assert.match(css, /\.reportCover\s*\{[\s\S]*?position:\s*relative/u);
  assert.match(css, /\.reportCoverImage\s*\{[\s\S]*?object-fit:\s*cover/u);
  assert.match(css, /\.reportCoverOverlay\s*\{[\s\S]*?position:\s*relative/u);
  assert.doesNotMatch(css, /url\("\/report-cover-planet\.png"\)/u);
});

test("does not leave primary strategy CTAs as dead buttons", () => {
  assert.match(component, /onAddToPlan/u);
  assert.match(component, /onShowEvidence/u);
  assert.match(component, /onAnswerQuestion/u);
  assert.match(component, /onDiscussStrategy/u);
  assert.match(component, /onShowDrafts/u);
  assert.match(component, /onReportPageChange/u);
  assert.match(component, /onAddEvidence/u);

  for (const deadButtonPattern of [
    /<button className=\{styles\.pinkButton\} type="button">\s*Добавить в план действий/u,
    /<button className=\{styles\.pinkButton\} type="button">Разобрать противоречие/u,
    /<button className=\{styles\.pinkButton\} type="button">Добавить данные для проверки/u,
    /<button className=\{styles\.outlineButton\} type="button">Показать основания/u,
    /<button className=\{styles\.outlineButton\} type="button">\{index === 2 \? "Добавить данные" : "Ответить"\}/u,
    /<button className=\{styles\.outlineButton\} type="button"><Sparkles aria-hidden="true" size=\{20\} \/>Обсудить стратегию с AI/u,
    /<button className=\{styles\.smallButton\} type="button">Как проверить/u,
    /<button className=\{styles\.smallButton\} type="button">Добавить/u,
    /<button className=\{styles\.outlineButton\} type="button">Сначала показать черновики/u,
    /<button className=\{styles\.outlineButton\} type="button">Предыдущая/u,
    /<button className=\{styles\.outlineButton\} type="button">Следующая/u,
  ]) {
    assert.doesNotMatch(component, deadButtonPattern);
  }

  assert.match(component, /onClick=\{onAddToPlan\} type="button">\s*Добавить в план действий/u);
  assert.match(component, /onClick=\{onShowEvidence\} type="button">Показать основания/u);
  assert.match(component, /onClick=\{onDiscussStrategy\} type="button"><Sparkles/u);
  assert.match(component, /onClick=\{\(\) => onPrepareAiAsset\?\.\("interview"\)\}/u);
  assert.match(component, /disabled=\{!canGoToPreviousReportPage\}/u);
  assert.match(component, /disabled=\{!canGoToNextReportPage\}/u);
});

test("keeps market labels semantically separated from values in the live desktop layout", () => {
  assert.match(component, /<strong>Целевой сегмент \(ICP\):<\/strong>\s*<span>/u);
  assert.match(component, /<strong>Отстройка:<\/strong>\s*<span>/u);
  assert.match(component, /<strong>Проверка:<\/strong>\s*<span>/u);
  assert.doesNotMatch(component, /<strong>Целевой сегмент \(ICP\)<\/strong><span>/u);
  assert.doesNotMatch(component, /<strong>Отстройка<\/strong><span>/u);
  assert.doesNotMatch(component, /<strong>Проверка<\/strong><span>/u);
});

test("second-pass strategy visuals remove producer strings and use owner-approved composition hooks", () => {
  assert.match(component, /function founderFacingEvidenceLabel/u);
  assert.match(component, /founderFacingEvidenceLabel\(row\[1\]/u);
  assert.match(component, /founderFacingEvidenceLabel\(row\[0\]/u);
  assert.doesNotMatch(component, /name:\s*safeText\(row\[1\]/u);
  assert.doesNotMatch(component, /type:\s*safeText\(row\[0\]/u);

  assert.match(component, /styles\.opportunityPanel/u);
  assert.match(component, /styles\.signalPanel/u);
  assert.match(css, /\.opportunityPanel\s*\{[\s\S]*?min-height:\s*260px/u);
  assert.match(css, /\.signalPanel\s*\{[\s\S]*?min-height:\s*260px/u);

  assert.match(component, /function founderRiskCard/u);
  assert.match(component, /riskCategoryTemplates/u);
  assert.match(component, /Финансы и запас времени/u);
  assert.match(component, /Продажи и GTM/u);
  assert.match(component, /Удержание и ценность/u);
  assert.doesNotMatch(component, /severity:\s*`Пробел \$\{index \+ 1\}`/u);

  assert.match(component, /styles\.actionLegend/u);
  assert.match(css, /\.page\[data-founder-strategy-page="action-plan"\]\s+\.priorityGrid\s*\{[\s\S]*?repeat\(5,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.actionLegend\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/u);

  assert.match(component, /src="\/report-cover-planet\.png"/u);
  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.reportCover\s*\{[\s\S]*?min-height:\s*470px/u);
  assert.match(css, /\.page\[data-founder-strategy-page="report-center"\]\s+\.formatCard\s*\{[\s\S]*?min-height:\s*158px/u);
});
