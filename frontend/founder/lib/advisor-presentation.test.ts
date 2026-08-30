import assert from "node:assert/strict";
import test from "node:test";

import {
  ADVISOR_DESKTOP_SEQUENCE,
  buildAdvisorAnswerPresentation,
  buildAdvisorQuestionImpactPresentation,
  buildAdvisorQuestionPresentation,
  buildAdvisorImprovementPresentation,
  safeFounderText,
} from "./advisor-presentation.ts";

const caseId = "11111111-1111-4111-8111-111111111111";
const proposalId = "22222222-2222-4222-8222-222222222222";

test("defines the 14 approved desktop advisor states in demo order", () => {
  assert.deepEqual(
    ADVISOR_DESKTOP_SEQUENCE.map((item) => item.id),
    [
      "start",
      "data-room",
      "progress-gate2",
      "overview",
      "next-question",
      "answer",
      "updated-analysis",
      "improved-plan",
      "metrics",
      "market",
      "risks",
      "action-plan",
      "report-center",
      "admin-proof",
    ],
  );
  assert.equal(ADVISOR_DESKTOP_SEQUENCE.every((item) => item.mobile === false), true);
  assert.doesNotMatch(
    ADVISOR_DESKTOP_SEQUENCE.map((item) => item.title).join(" "),
    /Admin proof|Gate/u,
  );
  assert.match(
    ADVISOR_DESKTOP_SEQUENCE.map((item) => item.title).join(" "),
    /Техническая проверка/u,
  );
});

test("builds one-best-question presentation with explicit public-research consent copy", () => {
  const presentation = buildAdvisorQuestionPresentation({
    case_id: caseId,
    status: "active",
    next_question: {
      question_id: `${caseId}:icp`,
      field_key: "icp",
      question_ru: "Кто платит за продукт и почему именно сейчас?",
      reason_ru: "Это уточнит ICP и приоритет канала продаж.",
      unlocks_ru: "После ответа можно пересчитать риск продаж.",
      answer_modes: ["manual", "file", "public_research", "skip"],
      origin: "document_gap",
      origin_label_ru: "Пробел в документе",
      context_ru: "Документ не подтверждает ICP.",
      answer_mode_labels_ru: {
        manual: "Ответить вручную",
        file: "Прикрепить файл",
        public_research: "Разрешить публичный поиск",
        skip: "Пропустить",
      },
    },
    answered_count: 1,
    total_count: 7,
  });

  assert.equal(presentation.statusLabel, "Вопрос 2 из 7");
  assert.equal(presentation.originLabel, "Пробел в документе");
  assert.equal(presentation.context, "Документ не подтверждает ICP.");
  assert.equal(presentation.publicResearchRequiresConsent, true);
  assert.match(presentation.privacyNote, /только после явного согласия/iu);
});

test("uses API origin and context instead of inferring from question text", () => {
  const presentation = buildAdvisorQuestionPresentation({
    case_id: caseId,
    status: "active",
    next_question: {
      question_id: `${caseId}:stage`,
      field_key: "stage",
      question_ru: "Какая у вас текущая выручка и модель ценообразования?",
      reason_ru: "Это нужно для текущего поля профиля.",
      unlocks_ru: "После ответа обновится стадия проекта.",
      answer_modes: ["manual", "skip"],
      origin: "document_contradiction",
      origin_label_ru: "Противоречие в документе",
      context_ru: "В материалах разные значения по стадии компании.",
      answer_mode_labels_ru: {
        manual: "Ответить вручную",
        file: "Прикрепить файл",
        public_research: "Разрешить публичный поиск",
        skip: "Пропустить",
      },
    },
    answered_count: 3,
    total_count: 9,
  });

  assert.equal(presentation.statusLabel, "Вопрос 4 из 9");
  assert.equal(presentation.originLabel, "Противоречие в документе");
  assert.equal(presentation.context, "В материалах разные значения по стадии компании.");
});

test("builds null question fallback without founder-visible internal markers", () => {
  const presentation = buildAdvisorQuestionPresentation(null);
  const rendered = JSON.stringify(presentation);

  assert.equal(presentation.statusLabel, "Вопрос уточняется");
  assert.doesNotMatch(rendered, /\b\d+\s+из\s+\d+\b/u);
  assert.doesNotMatch(
    rendered,
    /Advisor|Gate|Admin proof|progress-gate2|admin-proof|next-question|updated-analysis|MISSING|snapshot|hash|lineage|metricPackHash|snapshotHash/iu,
  );
  assert.match(rendered, /советник/iu);
});

test("builds question impacts from current field key instead of static preliminary inputs", () => {
  const pricing = buildAdvisorQuestionImpactPresentation({
    fieldKey: "pricing_revenue_model",
    originLabel: "Пробел в документе",
    context: "Документ не подтверждает модель выручки.",
    unlocks: "После ответа можно пересчитать MRR и маржу.",
  });
  const icp = buildAdvisorQuestionImpactPresentation({
    fieldKey: "icp",
    originLabel: "Пробел в документе",
    context: "Документ не подтверждает покупателя.",
    unlocks: "После ответа можно уточнить ICP.",
  });

  assert.notDeepEqual(
    pricing.map((item) => item.label),
    icp.map((item) => item.label),
  );
  assert.match(JSON.stringify(pricing), /Монетизация|MRR|маржа/u);
  assert.match(JSON.stringify(icp), /ICP|Клиент|сегмент/u);
  assert.doesNotMatch(
    JSON.stringify([pricing, icp]),
    /preliminaryInputs|Пилотные клиенты|Средний чек пилота|Ключевые метрики/u,
  );
});

test("never echoes manual answer text in updated-analysis presentation", () => {
  const manualAnswer = "У нас 82% retention и это нельзя повторить в интерфейсе.";
  const presentation = buildAdvisorAnswerPresentation(
    {
      case_id: caseId,
      question_id: `${caseId}:traction`,
      field_key: "traction",
      answer_type: "manual",
      status: "applied",
      confidence_delta: 9,
      analysis_blocked: false,
      answered_count: 3,
      total_count: 7,
      research_result: null,
      recalculation_status: "started",
      recalculation_data_revision: 2,
      recalculation_analysis_status: "gate2_preview_ready",
      recalculation_delta: {
        previous_revision: 1,
        new_revision: 2,
        fields_changed: ["traction"],
        core_coverage_delta: 1,
        conflicts_resolved: 1,
        conflicts_remaining: 0,
        calculations_recalculated: ["runway_months"],
        calculations_pending: ["report"],
      },
    },
    { manualAnswer },
  );

  const rendered = JSON.stringify(presentation);
  assert.doesNotMatch(rendered, /82% retention/u);
  assert.match(presentation.deltaLabel, /\+9/u);
  assert.equal(presentation.statusLabel, "Кейс обновлён; анализ ожидает подтверждения");
  assert.equal(presentation.revisionLabel, "Ревизия 1 → 2");
  assert.deepEqual(presentation.deltaRows.map((row) => row.label), [
    "Поля профиля",
    "Покрытие ядра",
    "Противоречия",
    "Расчёты",
  ]);
  assert.equal(presentation.nonBlocking, true);
});

test("does not claim recalculation when the canonical restart is deferred", () => {
  const presentation = buildAdvisorAnswerPresentation({
    case_id: caseId,
    question_id: `${caseId}:traction`,
    field_key: "traction",
    answer_type: "manual",
    status: "applied",
    confidence_delta: 0,
    analysis_blocked: false,
    answered_count: 3,
    total_count: 5,
    research_result: null,
    recalculation_status: "deferred",
    recalculation_data_revision: null,
    recalculation_analysis_status: null,
    recalculation_delta: null,
  });

  assert.equal(presentation.statusLabel, "Ответ сохранён; пересчёт отложен");
  assert.equal(presentation.revisionLabel, "Пересчёт отложен");
  assert.equal(presentation.deltaRows[0]?.value, "Нет пересчёта");
  assert.doesNotMatch(JSON.stringify(presentation), /Анализ пересчитан/u);
});

test("does not fabricate numeric progress or success when answer response is missing", () => {
  const presentation = buildAdvisorAnswerPresentation(null);
  const rendered = JSON.stringify(presentation);

  assert.equal(presentation.recalculationState, "none");
  assert.equal(presentation.progressLabel, "Ответ ещё не сохранён");
  assert.match(presentation.statusLabel, /нет сохранённого ответа/iu);
  assert.doesNotMatch(rendered, /\b0 из 5\b|Анализ обновлён|Кейс обновлён/iu);
});

test("maps recalculation codes to founder-facing labels and hides unknown raw ids", () => {
  const presentation = buildAdvisorAnswerPresentation({
    case_id: caseId,
    question_id: `${caseId}:pricing_revenue_model`,
    field_key: "pricing_revenue_model",
    answer_type: "manual",
    status: "applied",
    confidence_delta: 5,
    analysis_blocked: false,
    answered_count: 2,
    total_count: 8,
    research_result: null,
    recalculation_status: "started",
    recalculation_data_revision: 2,
    recalculation_analysis_status: "gate2_preview_ready",
    recalculation_delta: {
      previous_revision: 1,
      new_revision: 2,
      fields_changed: ["pricing_revenue_model", "safe_unknown_metric"],
      core_coverage_delta: 1,
      conflicts_resolved: 0,
      conflicts_remaining: 1,
      calculations_recalculated: ["runway_months", "ltv_cac_ratio", "safe_new_calc"],
      calculations_pending: ["report"],
    },
  });
  const rendered = JSON.stringify(presentation);

  assert.match(
    rendered,
    /Модель выручки и цена|Запас времени|ценность клиента \(LTV\) \/ стоимость привлечения \(CAC\)|ещё 1 поле|ещё 1 расчёт/u,
  );
  assert.doesNotMatch(
    rendered,
    /pricing_revenue_model|runway_months|ltv_cac_ratio|safe_unknown_metric|safe_new_calc/u,
  );
});

test("uses Russian-first labels for founder growth and financial impacts", () => {
  const financial = buildAdvisorQuestionImpactPresentation({
    fieldKey: "runway",
    originLabel: "Пробел в документе",
    context: "Нужно уточнить остаток денег и ежемесячные расходы.",
    unlocks: "После ответа обновится финансовый риск.",
  });
  const retention = buildAdvisorQuestionImpactPresentation({
    fieldKey: "churn",
    originLabel: "Пробел в документе",
    context: "Нужно уточнить повторные покупки.",
    unlocks: "После ответа обновится прогноз спроса.",
  });
  const rendered = JSON.stringify([financial, retention]);

  assert.match(rendered, /Запас времени/u);
  assert.match(rendered, /Темп расходов \/ стоимость привлечения \(CAC\)/u);
  assert.match(rendered, /Сигналы спроса/u);
  assert.match(rendered, /Удержание/u);
  assert.match(rendered, /Отток клиентов/u);
  assert.doesNotMatch(rendered, /Runway|Burn|Traction|Churn/u);
});

test("maps six proposals into accept reject version state without raw source details", () => {
  const presentation = buildAdvisorImprovementPresentation(
    {
      case_id: caseId,
      improvement_version: 6,
      proposals: Array.from({ length: 6 }, (_, index) => ({
        proposal_id: index === 0 ? proposalId : crypto.randomUUID(),
        target_area: ["POSITIONING", "MONETIZATION", "METRICS", "GTM", "RISK_REDUCTION", "INVESTOR_READINESS"][index],
        recommendation_ru: `Улучшить блок ${index + 1}.`,
        rationale_ru: `Пояснение для бизнеса ${index + 1}.`,
        expected_effect_ru: `Эффект для отчёта ${index + 1}.`,
        evidence_kinds: ["local_calculation", "live_inference"],
        confidence: 0.7,
      })),
    },
    {
      case_id: caseId,
      proposal_id: proposalId,
      decision: "accepted",
      previous_version: 6,
      new_version: 7,
      changed_fields: ["pricing_revenue_model"],
      recalculation_status: "started",
      recalculation_data_revision: 4,
      recalculation_analysis_status: "gate2_preview_ready",
    },
  );

  assert.equal(presentation.versionLabel, "Версия 7");
  assert.equal(
    presentation.decisionLabel,
    "Изменение принято; кейс обновлён и ожидает подтверждения Gate 2",
  );
  assert.equal(presentation.proposals.length, 6);
  assert.deepEqual(
    presentation.proposals.map((proposal) => proposal.actions),
    Array.from({ length: 6 }, () => ["Принять", "Отклонить"]),
  );
  assert.doesNotMatch(JSON.stringify(presentation), /sha256|trace|prompt|token|MISSING/iu);
});

test("only calls the project improved after a real accepted proposal advances the version", () => {
  const response = {
    case_id: caseId,
    improvement_version: 1,
    proposals: Array.from({ length: 6 }, (_, index) => ({
      proposal_id: index === 0 ? proposalId : crypto.randomUUID(),
      target_area: [
        "POSITIONING",
        "MONETIZATION",
        "METRICS",
        "GTM",
        "RISK_REDUCTION",
        "INVESTOR_READINESS",
      ][index],
      recommendation_ru: `Улучшить блок ${index + 1}.`,
      rationale_ru: `Пояснение ${index + 1}.`,
      expected_effect_ru: `Эффект ${index + 1}.`,
      evidence_kinds: ["local_calculation"],
      confidence: 0.7,
    })),
  } as const;

  const selectable = buildAdvisorImprovementPresentation(response);
  assert.equal(
    selectable.heroTitle,
    "Улучшения готовы к выбору — версия предложений 1",
  );

  const accepted = buildAdvisorImprovementPresentation(response, {
    case_id: caseId,
    proposal_id: proposalId,
    decision: "accepted",
    previous_version: 1,
    new_version: 2,
    changed_fields: ["positioning"],
    recalculation_status: "started",
    recalculation_data_revision: 4,
    recalculation_analysis_status: "gate2_preview_ready",
  });
  assert.equal(accepted.heroTitle, "Проект улучшен — версия 2");
});

test("keeps partial backend proposals exact instead of fabricating placeholder records", () => {
  const presentation = buildAdvisorImprovementPresentation({
    case_id: caseId,
    improvement_version: 3,
    proposals: Array.from({ length: 2 }, (_, index) => ({
      proposal_id: index === 0 ? proposalId : crypto.randomUUID(),
      target_area: ["POSITIONING", "MONETIZATION"][index],
      recommendation_ru: `Улучшить подтверждённый блок ${index + 1}.`,
      rationale_ru: `Пояснение для бизнеса ${index + 1}.`,
      expected_effect_ru: `Эффект для отчёта ${index + 1}.`,
      evidence_kinds: ["local_calculation"],
      confidence: 0.61,
    })),
  });

  assert.equal(presentation.proposals.length, 2);
  assert.deepEqual(
    presentation.proposals.map((proposal) => proposal.id.length > 0),
    [true, true],
  );
  assert.doesNotMatch(JSON.stringify(presentation), /"id":""|после анализа и ответа основателя|5 компаний|\$18 400|45%-70%|подтверждена|sha256|MISSING/iu);
});

test("safeFounderText masks unsafe fallback values instead of rendering raw internals", () => {
  assert.equal(safeFounderText(`sha256:${"a".repeat(64)}`), "Недостаточно данных");
  assert.equal(safeFounderText("D:\\Agents\\case\\deck.pdf"), "Недостаточно данных");
  assert.equal(safeFounderText("MISSING"), "Недостаточно данных");
  assert.equal(safeFounderText("Платят финансовые директора SMB"), "Платят финансовые директора SMB");
});
