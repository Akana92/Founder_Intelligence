import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("./founder-advisor-pages.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("./founder-advisor-pages.module.css", import.meta.url),
  "utf8",
);

function cssBlock(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} block should exist`);
  const end = css.indexOf("\n}", start);
  assert.notEqual(end, -1, `${selector} block should close`);
  return css.slice(start, end + 2);
}

test("exports the four approved AI advisor desktop pages and integration props", () => {
  for (const page of [
    "advisor_next_question",
    "advisor_answer",
    "advisor_updated_analysis",
    "advisor_improved_plan",
  ]) {
    assert.match(component, new RegExp(`"${page}"`, "u"));
    assert.match(
      component,
      new RegExp(`data-founder-advisor-page=[{"']${page.replaceAll("_", "-")}[}"']`, "u"),
    );
  }

  for (const exportedName of [
    "FounderAdvisorPageId",
    "FounderAdvisorPagesProps",
    "FounderAdvisorAnswerInput",
    "FounderAdvisorPages",
  ]) {
    assert.match(component, new RegExp(`export (?:type |function )${exportedName}`, "u"));
  }
  assert.match(component, /canApproveGate2\?:\s*boolean/u);
});

test("keeps Task 5 advisor workflow actions real and consent-gated", () => {
  for (const contract of [
    "onAdvisorAnswer",
    "onAdvisorImprovementDecision",
    "onAdvisorRetry",
    "publicResearchConsent",
    "consent_public_research",
    "answerType === \"public_research\" && !publicResearchConsent",
    "answerType === \"file\" && !selectedDocumentId",
    "answerType === \"manual\" && manualValue.trim() === \"\"",
  ]) {
    assert.match(component, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  for (const answerMode of ["manual", "file", "public_research", "skip"]) {
    assert.match(component, new RegExp(`type === "${answerMode}"`, "u"));
  }
});

test("uses live advisor presentations without leaking technical or private raw data", () => {
  for (const projection of [
    "buildAdvisorQuestionPresentation",
    "buildAdvisorAnswerPresentation",
    "buildAdvisorImprovementPresentation",
    "safeFounderText",
  ]) {
    assert.match(component, new RegExp(projection, "u"));
  }

  assert.match(component, /unsafeFounderPattern/u);
  assert.doesNotMatch(
    component,
    /snapshotHash|profileHash|metricPackHash|source_hashes|parse_inventory|artifact_hash|locator_hash|trace_ids|prompt_versions|raw excerpt|<code/iu,
  );
  assert.doesNotMatch(component, /\bMISSING\b|sha256:/iu);
});

test("does not hardcode demo readiness baselines without workspace evidence", () => {
  for (const forbidden of [
    "74 + growth",
    '"74%"',
    "82 + growth",
    '"82%"',
    "68 + Math.min",
    '"68"',
    ">82%<",
  ]) {
    assert.doesNotMatch(component, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  assert.match(component, /сейчас/u);
  assert.match(component, /после ответа/u);
  assert.match(component, /после отчёта/iu);
});

test("derives advisor copy from API field metadata instead of hardcoded retention", () => {
  for (const required of [
    "buildAdvisorQuestionContext",
    "pricing_revenue_model",
    "Модель выручки и цена",
    "Публичный поиск поможет найти аналоги цен",
  ]) {
    assert.match(component, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  assert.doesNotMatch(component, /question\?\.question_ru|question\?\.reason_ru|question\?\.unlocks_ru/u);
  assert.doesNotMatch(component, /categorySignals/u);
  for (const staleHardcode of [
    "Один показатель уточнит retention, LTV и устойчивость спроса",
    "60% продлевают через 3 месяца",
    "Внутренние retention-данные обычно не находятся в интернете",
    "Retention\", value: \"Будет пересчитано после сохранения",
  ]) {
    assert.doesNotMatch(
      component,
      new RegExp(staleHardcode.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"),
    );
  }
});

test("keeps generated advisor chrome Russian-first while preserving internal asset ids", () => {
  for (const copy of [
    "ИИ-советник",
    "Обсудить риск с ИИ",
    "Ответ на вопрос ИИ",
    "Попросить ИИ найти публичные данные",
    "Спросить ИИ-советника о проекте",
    "Обновлённый совет ИИ-советника",
    "Гипотеза ИИ",
    "Эксперимент с ценой",
    "Материалы, подготовленные ИИ",
    "целевой сегмент (ICP)",
    "ценность клиента (LTV)",
    "отток клиентов",
    "темп расходов",
    "остаток денег",
    "запас времени",
  ]) {
    assert.match(component, new RegExp(copy.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "iu"));
  }

  assert.doesNotMatch(
    component,
    /AI-советник|Обсудить риск с AI|Ответ на вопрос AI|Попросить AI|Спросить AI|совет AI|AI-гипотеза|Pricing-тест|Pricing-эксперимент|AI-подготовленные|live-доступ|current cash|monthly burn|unit economics|риск churn|label: "Retention"|label: "Traction"|label: "Runway"|label: "Burn"/iu,
  );
  assert.match(component, /type PreparedAssetId = "interview" \| "pricing" \| "positioning" \| "funnel"/u);
  assert.match(component, /asset: "pricing"/u);
});

test("keeps updated analysis advice relevant to the answered revenue pricing context", () => {
  for (const required of [
    "selectCategoryProposal",
    "answer.deltaRows.map",
    "answer.revisionLabel",
    "answer.recalculationState",
  ]) {
    assert.match(component, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  assert.doesNotMatch(component, /answerContext\.savedLabel|answerContext\.recalculationLabel|answerContext\.remainingInputLabel/u);
  assert.doesNotMatch(component, /advisorImprovements\?\.proposals\[0\]\?\.recommendation_ru/u);
});

test("matches the approved pink desktop advisor visual system through scoped css modules", () => {
  for (const selector of [
    ".page",
    ".hero",
    ".questionLayout",
    ".answerGrid",
    ".metricRibbon",
    ".updatedGrid",
    ".improvedGrid",
    ".timeline",
    ".pinkButton",
    ".glassPanel",
  ]) {
    assert.match(css, new RegExp(selector.replace(".", "\\."), "u"));
  }

  assert.match(css, /--advisor-pink:\s*var\(--fi-accent\)/u);
  assert.match(css, /--advisor-border:\s*var\(--fi-border\)/u);
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /border:\s*1px solid var\(--advisor-border\)/u);
  assert.doesNotMatch(css, /position:\s*fixed|width:\s*100vw|height:\s*100vh/u);
});

test("keeps advisor screens compact enough for one approved desktop viewport", () => {
  for (const oversizedRule of [
    "font-size: clamp(36px, 4.4vw, 66px)",
    "font-size: clamp(26px, 3vw, 44px)",
    "font-size: 38px",
    "font-size: 42px",
    "min-height: 380px",
    "min-height: 112px",
    "min-height: 96px",
  ]) {
    assert.doesNotMatch(css, new RegExp(oversizedRule.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  assert.match(css, /max-width:\s*1248px/u);
  assert.match(css, /font-size:\s*clamp\(28px,\s*2\.4vw,\s*42px\)/u);
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1\.55fr\)\s+minmax\(260px,\s*0\.7fr\)/u);
  assert.match(css, /grid-template-columns:\s*20px\s+44px\s+minmax\(0,\s*1fr\)\s+auto/u);
});

test("owner rework keeps screens 11-14 dense, mockup-led, and same-case honest", () => {
  for (const className of [
    "advisorQuestionCanvas",
    "advisorAnswerCanvas",
    "advisorUpdatedCanvas",
    "advisorImprovedCanvas",
    "advisorSummaryRail",
    "advisorKnownStrip",
    "questionFocusColumn",
    "questionFocusCard",
    "metricRailCompact",
    "answerModePanel",
    "answerImpactPanel",
    "answerModeRow",
    "answerCtaStack",
    "updatedMetricRibbon",
    "updatedSummaryBand",
    "updatedDetailStack",
    "updatedAdviceColumn",
    "improvedEvidenceDeck",
    "improvedTopBand",
    "improvedMiddleBand",
    "improvedBottomBand",
    "proposalDecisionPanel",
    "proposalDecisionGrid",
    "proposalDecisionItem",
    "proposalCompactGrid",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(css, /\.page\s*\{[\s\S]*?max-width:\s*1248px/u);
  assert.doesNotMatch(cssBlock(".page"), /max-height:\s*calc\(1000px - 132px\)|overflow:\s*hidden/u);
  assert.match(css, /\.advisorQuestionCanvas\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.34fr\)\s+minmax\(310px,\s*0\.66fr\)/u);
  assert.match(css, /\.advisorQuestionCanvas\s*\{[\s\S]*?min-height:\s*560px/u);
  assert.match(css, /\.questionFocusCard\s*\{[\s\S]*?min-height:\s*0/u);
  assert.match(css, /\.metricRailCompact\s*\{[\s\S]*?min-height:\s*560px/u);
  assert.match(css, /\.advisorKnownStrip\s*\{[\s\S]*?min-height:\s*140px/u);
  assert.match(css, /advisor-next-question[\s\S]*?\.actionRow\s*\{[\s\S]*?grid-template-columns:/u);
  assert.match(css, /\.advisorAnswerCanvas\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.08fr\)\s+minmax\(340px,\s*0\.82fr\)/u);
  assert.match(css, /\.advisorAnswerCanvas\s*\{[\s\S]*?min-height:\s*720px/u);
  assert.match(css, /\.answerModePanel\s*\{[\s\S]*?padding:\s*24px/u);
  assert.match(css, /\.answerImpactPanel\s*\{[\s\S]*?padding:\s*24px/u);
  assert.match(css, /\.answerModeRow\s*\{[\s\S]*?min-height:\s*92px/u);
  assert.match(css, /\.answerCtaStack\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+auto\s+auto\s+auto/u);
  assert.match(css, /\.advisorUpdatedCanvas\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*0\.94fr\)\s+minmax\(360px,\s*0\.86fr\)/u);
  assert.match(css, /\.advisorUpdatedCanvas\s*\{[\s\S]*?min-height:\s*500px/u);
  assert.match(css, /\.updatedSummaryBand\s*\{[\s\S]*?min-height:\s*150px/u);
  assert.match(css, /\.updatedSummaryBand\s+\.impactStat\s*\{[\s\S]*?box-shadow:\s*none/u);
  assert.match(css, /\.updatedAdviceColumn\s*\{[\s\S]*?min-height:\s*500px/u);
  assert.match(css, /\.advisorImprovedCanvas\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+auto\s+auto/u);
  assert.match(css, /\.improvedTopBand\s*\{[\s\S]*?min-height:\s*166px/u);
  assert.match(css, /\.improvedMiddleBand\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.improvedMiddleBand\s*\{[\s\S]*?min-height:\s*216px/u);
  assert.match(css, /\.improvedBottomBand\s*\{[\s\S]*?min-height:\s*228px/u);
  assert.match(css, /\.proposalDecisionGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.proposalDecisionItem\s*\{[\s\S]*?min-height:\s*76px/u);
  assert.match(css, /\.proposalCompactGrid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.proposalDecisionPanel\s*\{[\s\S]*?grid-column:\s*1\s*\/\s*-1/u);
  assert.match(css, /\.evidenceStatePanel\s*\{[\s\S]*?grid-template-columns:\s*1fr/u);
  assert.match(css, /\.evidenceOverview\s*\{[\s\S]*?grid-template-columns:\s*98px\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /advisor-improved-plan[\s\S]*?\.proposalDecisionItem\s*\{[\s\S]*?grid-template-columns:\s*30px\s+minmax\(0,\s*1fr\)\s+auto/u);
  assert.match(css, /advisor-improved-plan[\s\S]*?\.proposalDecisionItem\s+p\s*\{[\s\S]*?-webkit-line-clamp:\s*2/u);
  assert.match(css, /advisor-improved-plan[\s\S]*?\.proposalDecisionItem\s+\.outlineButton\s*\{[\s\S]*?min-height:\s*28px/u);
  assert.match(css, /advisor-improved-plan[\s\S]*?\.proposalDecisionItem\s+\.actionRow\s*\{[\s\S]*?grid-column:\s*auto/u);
  assert.match(css, /\.planCard\s*\{[\s\S]*?min-height:\s*0/u);
  assert.match(css, /\.planCard\s*\{[\s\S]*?padding:\s*10px/u);
  assert.match(css, /\.timelineMilestone\s*\{[\s\S]*?min-height:\s*168px/u);
  assert.doesNotMatch(css, /min-height:\s*132px/u);
  assert.doesNotMatch(css, /min-height:\s*142px/u);
});

test("screen 11 uses the approved unframed canvas and vertical metric rail", () => {
  assert.doesNotMatch(cssBlock(".page"), /^\s*(background|border|border-radius):/mu);
  assert.match(component, /styles\.advisorStepPill/u);
  assert.match(
    component,
    /className=\{`\$\{styles\.glassPanel\} \$\{styles\.questionFocusColumn\} \$\{styles\.advisorSummaryRail\}`\}/u,
  );
  assert.match(component, /styles\.questionFocusCard/u);
  assert.match(component, /styles\.metricRailCompact/u);
  assert.match(css, /\.advisorStepPill\s*\{[\s\S]*?border-radius:\s*999px/u);
  assert.doesNotMatch(component, /Шаг 1 из 4 для повышения точности/u);
  assert.match(component, /question\.statusLabel/u);
  assert.match(component, /question\.originLabel/u);
  assert.match(component, /question\.context/u);
  assert.match(component, /className=\{`\$\{styles\.glassPanel\} \$\{styles\.metricRailPanel\} \$\{styles\.metricRailCompact\} \$\{styles\.advisorSummaryRail\}`\}/u);
  assert.match(component, /className=\{`\$\{styles\.metricRibbon\} \$\{styles\.metricRail\}`\}/u);
  assert.match(component, /questionImpactRows\.map/u);
  assert.match(css, /\.metricRail\s*\{[\s\S]*?grid-template-columns:\s*1fr/u);
  assert.match(css, /\.metricRail\s+\.impactStat\s*\{[\s\S]*?grid-template-columns:\s*64px\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.metricRing\s*\{[\s\S]*?border-radius:\s*999px/u);
});

test("screen 11 keeps one question inside a unified, centered decision surface", () => {
  assert.doesNotMatch(
    component,
    /<AdvisorHero\s+eyebrow=\{question\.statusLabel\}[\s\S]*?title="AI-советник"/u,
  );
  assert.match(
    component,
    /subtitle="Система задаёт один вопрос, который сильнее всего улучшит анализ сейчас"/u,
  );
  assert.match(
    component,
    /className=\{`\$\{styles\.glassPanel\} \$\{styles\.questionFocusColumn\} \$\{styles\.advisorSummaryRail\}`\}/u,
  );
  assert.doesNotMatch(
    component,
    /<section className=\{`\$\{styles\.glassPanel\} \$\{styles\.questionCard\} \$\{styles\.questionFocusCard\}`\}>/u,
  );
  assert.match(
    css,
    /\.questionFocusColumn\s*\{[\s\S]*?min-height:\s*560px[\s\S]*?padding:\s*24px/u,
  );
  assert.match(
    css,
    /\.questionFocusColumn\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+auto/u,
  );
  assert.match(css, /\.questionFocusCard\s*\{[\s\S]*?min-height:\s*0/u);
  assert.match(
    css,
    /\.page\[data-founder-advisor-page="advisor-next-question"\]\s+\.questionFocusCard\s*>\s*\.roundIcon\s*\{[\s\S]*?align-self:\s*start[\s\S]*?height:\s*64px[\s\S]*?width:\s*64px/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-advisor-page="advisor-next-question"\]\s+\.unlockGrid\s+article\s*\{[\s\S]*?display:\s*grid[\s\S]*?min-height:\s*84px[\s\S]*?place-items:\s*center/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-advisor-page="advisor-next-question"\]\s+\.metricRailCompact\s+\.impactStat\s*\{[\s\S]*?background:\s*transparent[\s\S]*?border:\s*0[\s\S]*?box-shadow:\s*none/u,
  );
  assert.match(
    css,
    /\.page\[data-founder-advisor-page="advisor-next-question"\]\s+\.metricRailCompact\s+\.metricRing\s*\{[\s\S]*?align-self:\s*center[\s\S]*?display:\s*grid[\s\S]*?height:\s*72px[\s\S]*?place-items:\s*center[\s\S]*?width:\s*72px/u,
  );
});

test("screen 12 shows manual input by default and public consent only in research mode", () => {
  assert.match(component, /styles\.answerModeRow/u);
  assert.match(component, /className=\{`\$\{styles\.glassPanel\} \$\{styles\.answerImpactPanel\} \$\{styles\.answerCtaStack\}`\}/u);
  assert.match(component, /selectedMode === "manual" \? \(/u);
  assert.match(component, /selectedMode === "public_research" \? \(\s*<label\s+className=\{styles\.consentBox\}/u);
  assert.match(component, /Публичный поиск запускается отдельно/u);
  assert.doesNotMatch(component, /<label\s+className=\{styles\.consentBox\}[\s\S]*?<\/label>\s*<p className=\{styles\.privacyNote\}>/u);
  assert.doesNotMatch(component, /<Radio\s+aria-hidden="true"/u);
  assert.match(component, /className=\{styles\.modeSelector\}/u);
  assert.match(
    component,
    /className=\{`\$\{styles\.answerModeGroup\} \$\{selectedMode === "manual" \? styles\.answerModeGroupActive : ""\}`\}/u,
  );
  assert.match(
    css,
    /\.modeSelector\s*\{[\s\S]*?display:\s*grid[\s\S]*?height:\s*24px[\s\S]*?place-items:\s*center[\s\S]*?width:\s*24px/u,
  );
  assert.match(
    css,
    /\.modeCard\[aria-pressed="true"\]\s+\.modeSelector::after\s*\{[\s\S]*?opacity:\s*1/u,
  );
  assert.match(
    css,
    /\.answerModeGroupActive\s*\{[\s\S]*?border-color:\s*var\(--advisor-pink\)[\s\S]*?box-shadow:/u,
  );
  assert.match(
    css,
    /\.answerCtaStack\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+auto\s+auto\s+auto/u,
  );
  assert.match(
    component,
    /className=\{styles\.manualInput\}[\s\S]*?<textarea[\s\S]*?rows=\{2\}/u,
  );
  assert.match(
    css,
    /\.manualInput textarea\s*\{[\s\S]*?line-height:\s*1\.4[\s\S]*?resize:\s*none/u,
  );
  assert.match(
    css,
    /\.answerCtaStack\s+\.impactRow em\s*\{[\s\S]*?font-size:\s*12px[\s\S]*?white-space:\s*nowrap/u,
  );
  assert.match(
    css,
    /\.answerCtaStack\s+\.pinkButton:disabled\s*\{[\s\S]*?background:\s*rgba\(245,\s*161,\s*207,\s*0\.16\)[\s\S]*?opacity:\s*1/u,
  );
  assert.match(
    css,
    /\.answerModeRow\s+\.modeIcon svg\s*\{[\s\S]*?transform:\s*translate\(0\.5px,\s*0\.75px\)/u,
  );
});

test("screen 12 renders semantic mismatch beside the manual input and keeps failed save local", () => {
  const pageStart = component.indexOf("function AnswerPage(");
  const pageEnd = component.indexOf("function UpdatedAnalysisPage(", pageStart);
  assert.notEqual(pageStart, -1);
  assert.notEqual(pageEnd, -1);
  const pageBlock = component.slice(pageStart, pageEnd);

  assert.match(pageBlock, /advisor_manual_answer_semantic_mismatch/u);
  assert.match(pageBlock, /Ответ не подходит к текущему вопросу/u);
  assert.match(pageBlock, /const saved = await props\.onAdvisorAnswer/u);
  assert.match(pageBlock, /if \(saved\) \{/u);
  assert.match(pageBlock, /setManualValue\(""\)/u);
  assert.match(pageBlock, /manualInputError/u);
  assert.match(css, /\.manualInputError\s*\{/u);
});

test("screen 12 does not convert every failed manual save into semantic mismatch", () => {
  const pageStart = component.indexOf("function AnswerPage(");
  const pageEnd = component.indexOf("function UpdatedAnalysisPage(", pageStart);
  assert.notEqual(pageStart, -1);
  assert.notEqual(pageEnd, -1);
  const pageBlock = component.slice(pageStart, pageEnd);

  assert.match(pageBlock, /advisorErrorCode\(props\.workspace\?\.advisorError\)/u);
  assert.doesNotMatch(
    pageBlock,
    /if \(answerType === "manual"\) \{\s*setLocalManualError\("advisor_manual_answer_semantic_mismatch"\);/u,
  );
  assert.match(pageBlock, /generalAnswerError/u);
  assert.match(pageBlock, /Не удалось сохранить ответ/u);
});

test("question and answer rails derive from current advisor API state instead of static ribbons", () => {
  assert.doesNotMatch(component, /const preliminaryInputs/u);
  assert.doesNotMatch(component, /function MetricRibbon/u);
  assert.doesNotMatch(component, /<MetricRibbon/u);
  assert.match(component, /buildAdvisorQuestionImpactPresentation/u);
  assert.match(component, /questionImpactRows/u);

  const pageStart = component.indexOf("function NextQuestionPage(");
  const pageEnd = component.indexOf("function AnswerModeCard(", pageStart);
  assert.notEqual(pageStart, -1);
  assert.notEqual(pageEnd, -1);
  const pageBlock = component.slice(pageStart, pageEnd);
  assert.match(pageBlock, /questionImpactRows\.map/u);
  assert.match(pageBlock, /question\.originLabel/u);
  assert.match(pageBlock, /question\.context/u);
  assert.doesNotMatch(pageBlock, /Пилотные клиенты|Средний чек пилота|Ключевые метрики/u);
});

test("screen 13 hands off to the improved plan once six real proposals are ready", () => {
  assert.match(component, /className=\{`\$\{styles\.glassPanel\} \$\{styles\.updatedMetricRibbon\} \$\{styles\.updatedSummaryBand\}`\}/u);
  assert.match(component, /className=\{`\$\{styles\.stack\} \$\{styles\.updatedDetailStack\}`\}/u);
  assert.match(component, /styles\.updatedAdviceColumn/u);
  assert.match(component, /updatedHeroCopy\[answer\.recalculationState\]\.title/u);
  assert.match(component, /className=\{styles\.updatedSourceStrip\}/u);
  assert.match(component, /answer\.deltaRows\.slice\(0,\s*3\)\.map/u);
  assert.match(component, /const hasConfirmedImprovementProposals =\s*props\.workspace\?\.advisorImprovements\?\.proposals\.length === 6/u);
  assert.match(
    component,
    /const isAwaitingRecalculationConfirmation =\s*recalculationStarted &&\s*!hasConfirmedImprovementProposals &&\s*Boolean\(props\.onContinueRecalculation\)/u,
  );
  assert.match(
    component,
    /const canContinueRecalculation =\s*isAwaitingRecalculationConfirmation &&\s*props\.workspace\?\.canApproveGate2 === true/u,
  );
  assert.match(
    component,
    /isBusy\s*\?\s*busyCopy\s*:\s*isAwaitingRecalculationConfirmation\s*\?\s*"Продолжить обновление"/u,
  );
  assert.match(component, /props\.onContinueRecalculation/u);
  assert.doesNotMatch(component, /className=\{styles\.metricDelta\}/u);
  assert.doesNotMatch(component, /п\.п\./u);
  assert.match(component, /answer\.deltaRows\.map/u);
  assert.match(component, /Требует подтверждения/u);
  assert.match(component, /answer\.recalculationState/u);
  assert.match(css, /\.metricSegmented\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/u);
  assert.match(css, /\.page\[data-founder-advisor-page="advisor-updated-analysis"\]\s+\.updatedMetricRibbon[\s\S]*?min-height:\s*110px/u);
  assert.match(css, /\.page\[data-founder-advisor-page="advisor-updated-analysis"\]\s+\.metricSegmented\s+\.impactStat\s*\{[\s\S]*?grid-template-columns:\s*66px\s+minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.page\[data-founder-advisor-page="advisor-updated-analysis"\]\s+\.metricRing\s*\{[\s\S]*?height:\s*64px[\s\S]*?place-items:\s*center[\s\S]*?width:\s*64px/u);
  assert.match(css, /\.updatedAdviceColumn\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+auto\s+auto/u);
  assert.match(css, /\.updatedAdviceColumn\s*\{[\s\S]*?align-content:\s*start/u);
  assert.doesNotMatch(cssBlock(".updatedAdviceColumn"), /grid-template-rows:\s*auto\s+1fr\s+auto\s+auto/u);
  assert.match(css, /\.updatedAdviceCard\s*\{[\s\S]*?place-items:\s*center/u);
  assert.match(css, /advisor-updated-analysis["']\]\s+\.updatedSourceStrip\s*\{[\s\S]*?min-height:\s*34px/u);
  for (const className of [
    "updatedConfirmedPanel",
    "updatedRecalculatedPanel",
    "updatedRiskPanel",
    "updatedAdviceCard",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }
});

test("screen 13 title and status branch on recalculation state instead of started boolean", () => {
  const pageStart = component.indexOf("function UpdatedAnalysisPage(");
  const pageEnd = component.indexOf("function ImprovedPlanPage(", pageStart);
  assert.notEqual(pageStart, -1);
  assert.notEqual(pageEnd, -1);
  const pageBlock = component.slice(pageStart, pageEnd);

  assert.match(pageBlock, /updatedHeroCopy/u);
  assert.match(pageBlock, /answer\.recalculationState/u);
  assert.doesNotMatch(
    pageBlock,
    /title=\{recalculationStarted \? "Анализ обновляется" : "Анализ обновлён"\}/u,
  );
  assert.match(pageBlock, /Ответ сохранён, пересчёт отложен/u);
  assert.match(pageBlock, /Ответ сохранён без пересчёта/u);
});

test("screen 13 keeps the answered category after the next-question payload is refreshed", () => {
  const contextStart = component.indexOf("function buildAdvisorQuestionContext(");
  const contextEnd = component.indexOf("function categoryTextMatches(", contextStart);
  assert.notEqual(contextStart, -1);
  assert.notEqual(contextEnd, -1);
  const contextBlock = component.slice(contextStart, contextEnd);

  assert.match(contextBlock, /workspace\?\.advisorAnswer\?\.field_key/u);
  assert.match(contextBlock, /question\?\.field_key/u);
  assert.doesNotMatch(contextBlock, /answer_ru/u);
});

test("screen 13 centers circular status icons and keeps founder copy free of internal gate names", () => {
  const pageStart = component.indexOf("function UpdatedAnalysisPage(");
  const pageEnd = component.indexOf("function ImprovedPlanPage(", pageStart);
  assert.notEqual(pageStart, -1);
  assert.notEqual(pageEnd, -1);
  const pageBlock = component.slice(pageStart, pageEnd);

  assert.doesNotMatch(pageBlock, /Gate 2/u);
  assert.match(pageBlock, /className=\{styles\.resultIcon\}/u);
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.metricRing\s*\{[\s\S]*?display:\s*grid[\s\S]*?height:\s*64px[\s\S]*?place-items:\s*center[\s\S]*?width:\s*64px/u,
  );
  assert.match(css, /advisor-updated-analysis["']\]\s+\.progressBar\s*\{[\s\S]*?display:\s*none/u);
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.impactStat strong\s*\{[\s\S]*?flex-wrap:\s*nowrap[\s\S]*?font-size:\s*22px[\s\S]*?white-space:\s*nowrap/u,
  );
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.updatedDetailStack\s+\.resultRow\s*\{[\s\S]*?display:\s*grid[\s\S]*?grid-template-columns:\s*42px\s+minmax\(0,\s*1fr\)\s+auto/u,
  );
  assert.match(
    css,
    /\.resultIcon\s*\{[\s\S]*?display:\s*grid[\s\S]*?height:\s*48px[\s\S]*?place-items:\s*center[\s\S]*?width:\s*48px/u,
  );
  assert.match(pageBlock, /className=\{styles\.resultText\}/u);
  assert.match(css, /advisor-updated-analysis["']\]\s+\.updatedMetricRibbon[\s\S]*?min-height:\s*110px/u);
  assert.match(css, /\.updatedAdviceCard\s*\{[\s\S]*?min-height:\s*340px/u);
  assert.match(css, /advisor-updated-analysis["']\]\s+\.updatedSourceStrip\s*\{[\s\S]*?min-height:\s*34px/u);
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.updatedAdviceCard\s+\.kicker\s*\{[\s\S]*?text-transform:\s*none/u,
  );
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.updatedAdviceCard\s+h2\s*\{[\s\S]*?font-size:\s*22px[\s\S]*?line-height:\s*1\.18[\s\S]*?max-width:\s*380px/u,
  );
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.updatedAdviceColumn\s+\.pinkButton:not\(:disabled\)\s*\{[\s\S]*?box-shadow:/u,
  );
  assert.match(
    css,
    /advisor-updated-analysis["']\]\s+\.updatedAdviceCard\s*>\s*em\s*\{[\s\S]*?display:\s*inline-flex[\s\S]*?font-style:\s*normal/u,
  );
});

test("screen 14 exposes before-after, monetization, evidence, connected timeline, and prepared assets", () => {
  for (const className of [
    "improvedTopActions",
    "improvedPlanLayout",
    "icpPanel",
    "pricingPanel",
    "monetizationPanel",
    "evidenceStatePanel",
    "evidenceScore",
    "timelineMilestone",
    "timelineConnected",
    "improvedTimelinePanel",
    "improvedAssetsPanel",
    "proposalDecisionPanel",
    "proposalDecisionGrid",
    "proposalDecisionItem",
    "preparedAssetList",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  assert.match(component, /<section className=\{`\$\{styles\.glassPanel\} \$\{styles\.improvedTimelinePanel\}`\}>/u);
  assert.match(component, /<section className=\{`\$\{styles\.glassPanel\} \$\{styles\.improvedAssetsPanel\}`\}>/u);
  assert.doesNotMatch(component, /className=\{`\$\{styles\.glassPanel\} \$\{styles\.improvedBottomBand\}/u);

  for (const copy of [
    "Было",
    "Стало",
    "Обновлённая монетизация",
    "Обновлённый целевой сегмент (ICP)",
    "Эксперимент с ценой",
    "Состояние доказательств",
    "План 7 / 30 / 60 / 90 дней",
    "Материалы, подготовленные ИИ",
    "На основе подтверждённого ответа",
  ]) {
    assert.match(
      component,
      new RegExp(copy.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"),
    );
  }
});

test("locks advisor actions and shows readable progress while an async request is running", () => {
  assert.match(component, /busy\?:\s*boolean/u);
  assert.match(component, /busyLabel\?:\s*string/u);
  assert.match(component, /const isBusy = Boolean\(workspace\?\.busy\)/u);
  assert.match(component, /const busyCopy = workspace\?\.busyLabel \?\? "Идёт обработка…"/u);
  assert.match(component, /disabled=\{isBusy \|\| !canAnswer\}/u);
  assert.match(component, /disabled=\{isBusy \|\| !canSave\}/u);
  assert.match(component, /\{isBusy \? busyCopy : "Сохранить и пересчитать"\}/u);
  assert.match(component, /disabled=\{isBusy \|\| !canDecideAdvisorProposals \|\| !props\.onAdvisorImprovementDecision\}/u);
  assert.match(component, /disabled=\{isBusy \|\| !props\.onOpenPreparedAsset\}/u);
});

test("screen 14 keeps attention on the verified change and renders a real proposal-backed plan", () => {
  for (const className of [
    "improvedFocusPanel",
    "centeredIcon",
    "changeFlowArrow",
    "metricSignal",
    "evidenceLegendRow",
    "evidenceConfidenceStrip",
    "timelineContent",
    "timelineStatus",
    "assetAvailability",
    "improvedActionHint",
  ]) {
    assert.match(component, new RegExp(`styles\\.${className}`, "u"));
    assert.match(css, new RegExp(`\\.${className}\\s*\\{`, "u"));
  }

  for (const icon of [
    "CircleDollarSign",
    "CircleCheckBig",
    "CircleDotDashed",
    "Funnel",
    "LockKeyhole",
    "Target",
  ]) {
    assert.match(component, new RegExp(`\\b${icon}\\b`, "u"));
  }

  assert.match(component, /const timelineProposals = proposalCards\.slice\(0,\s*4\)/u);
  assert.match(component, /founderLabelForTarget\(proposal\.target\)/u);
  assert.match(component, /compactFounderSafe\(proposal\.expectedEffect/u);
  assert.match(component, /const preparedAssets:/u);
  assert.doesNotMatch(component, />После выбора улучшений</u);
  assert.match(
    css,
    /\.centeredIcon\s*\{[\s\S]*?display:\s*grid[\s\S]*?line-height:\s*0[\s\S]*?place-items:\s*center/u,
  );
  assert.match(css, /\.centeredIcon\s+svg\s*\{[\s\S]*?display:\s*block/u);
  assert.match(
    css,
    /\.improvedFocusPanel\s*\{[\s\S]*?border-color:\s*rgba\(245,\s*161,\s*207,[\s\S]*?box-shadow:/u,
  );
});

test("screen 14 keeps six real proposal decisions in a compact disclosure above the approved plan", () => {
  assert.match(component, /<details className=\{styles\.proposalDecisionDisclosure\}>/u);
  assert.match(component, /<summary className=\{styles\.proposalDecisionSummary\}>/u);
  assert.match(component, /6 проверяемых предложений/u);
  assert.match(component, /Откройте, чтобы принять или отклонить каждое/u);
  assert.doesNotMatch(component, /<details[^>]*\sopen(?:=|\s|>)/u);
  assert.match(component, /className=\{styles\.proposalDecisionPanel\}/u);
  assert.match(component, /className=\{`\$\{styles\.proposalDecisionGrid\} \$\{styles\.proposalCompactGrid\}`\}/u);
  assert.match(component, /className=\{styles\.proposalDecisionItem\}/u);
  assert.match(component, /proposalCards\.slice\(0,\s*6\)\.map\(\(proposal,\s*index\) => \(/u);
  assert.match(component, /props\.onAdvisorImprovementDecision\?\.\(proposal\.id,\s*"accepted"\)/u);
  assert.match(component, /props\.onAdvisorImprovementDecision\?\.\(proposal\.id,\s*"rejected"\)/u);
  assert.match(css, /\.proposalDecisionDisclosure\s*\{[\s\S]*?border-radius:\s*16px/u);
  assert.match(css, /\.proposalDecisionSummary\s*\{[\s\S]*?min-height:\s*52px/u);
  assert.match(css, /\.proposalDecisionSummary\s*\{[\s\S]*?grid-template-columns:\s*38px\s+minmax\(0,\s*1fr\)\s+auto/u);
  assert.doesNotMatch(component, /<ProposalCard[\s\S]*?proposal=\{proposal\}/u);
});

test("screen 14 translates every typed improvement target into founder-facing Russian", () => {
  for (const [target, label] of [
    ["positioning", "Позиционирование"],
    ["monetization", "Монетизация"],
    ["metrics", "Метрики"],
    ["gtm", "Выход на рынок"],
    ["risk_reduction", "Снижение рисков"],
    ["investor_readiness", "Инвестиционная готовность"],
  ]) {
    assert.match(component, new RegExp(`"${target}": "${label}"`, "u"));
  }
  assert.match(component, /return founderTargetLabels\[normalized\]/u);
});

test("screen 11-14 never show unverified demo claims and render all six backend proposals", () => {
  for (const forbiddenClaim of [
    "5 компаний",
    "$18 400",
    "45%-70%",
    "Устойчивость спроса:",
    "высокий риск",
    "средний</span>",
    "Соответствие боли: высокое",
    "Бюджетная готовность: высокая",
    "Готовность платить: подтверждена",
    "Цена за 100 процессов",
    "Текущий payback",
    "В работе",
    "Запланировано",
    "Что пересчитано",
  ]) {
    assert.doesNotMatch(
      component,
      new RegExp(forbiddenClaim.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"),
    );
  }

  assert.doesNotMatch(component, /proposalCards\.slice\(0,\s*2\)/u);
  assert.match(component, /proposalCards\.slice\(0,\s*6\)/u);
  assert.doesNotMatch(component, /key=\{proposal\.id\}/u);
  assert.match(component, /key=\{proposal\.id \|\| `\$\{proposal\.target\}-\$\{index\}`\}/u);
  assert.doesNotMatch(component, /Array\.from\(\{\s*length:\s*6\s*\}/u);
  assert.doesNotMatch(component, /readonly-\$\{index\}/u);
  assert.match(component, /const proposalCards = improvements\.proposals/u);
  assert.match(component, /Шесть проверяемых улучшений появятся после канонического отчёта этого же кейса/u);
  assert.match(component, /Требует подтверждения/u);
  assert.match(component, /\["Проверяемая цена",\s*"Требует подтверждения"\]/u);
  assert.match(component, /const timelineProposals = proposalCards\.slice\(0,\s*4\)/u);
  assert.match(component, /После выбора решений/u);
  assert.doesNotMatch(component, /Анализ обновляется/u);
  assert.match(component, /Профиль обновлён, отчёт ожидает пересчёта/u);
  assert.match(component, /Статус пересчёта/u);
});

test("keeps advisor provenance wording honest about document statements", () => {
  assert.match(component, /Заявлено/u);
  assert.match(component, /Указано в материалах кейса/u);
  assert.match(component, /На данных, заявленных в документах/u);
  assert.doesNotMatch(component, /<strong>Факт<\/strong>|На подтверждённых данных/u);
});

test("keeps unsupported advisor actions visibly disabled instead of rendering inert CTAs", () => {
  for (const callback of [
    "props.onAddData",
    "props.onApplyToReport",
    "props.onReturnPreviousVersion",
    "props.onOpenPreparedAsset",
  ]) {
    assert.match(
      component,
      new RegExp(`disabled=\\{isBusy \\|\\| !${callback.replace(".", "\\.")}\\}`, "u"),
    );
  }
  assert.match(css, /\.assetRow:disabled[\s\S]*?opacity:\s*0\.45/u);
});
