import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiContractError,
  parseAdvisorAnswerResponse,
  parseAdvisorImprovementsResponse,
  parseAdvisorNextQuestionResponse,
  parseAdvisorImprovementDecisionResponse,
} from "./contracts.ts";

const caseId = "11111111-1111-4111-8111-111111111111";
const proposalId = "22222222-2222-4222-8222-222222222222";

test("parses the Task 5 advisor next-question contract exactly", () => {
  const response = parseAdvisorNextQuestionResponse({
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
      context_ru: "Документ описывает продукт, но не называет покупателя.",
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

  assert.equal(response.status, "active");
  assert.equal(response.next_question?.field_key, "icp");
  assert.equal(response.next_question?.origin, "document_gap");
  assert.equal(response.next_question?.origin_label_ru, "Пробел в документе");
  assert.equal(
    response.next_question?.context_ru,
    "Документ описывает продукт, но не называет покупателя.",
  );
  assert.equal(response.total_count, 7);
  assert.deepEqual(response.next_question?.answer_modes, [
    "manual",
    "file",
    "public_research",
    "skip",
  ]);
});

test("parses advisor answer deltas without requiring manual answer echo", () => {
  const response = parseAdvisorAnswerResponse({
    case_id: caseId,
    question_id: `${caseId}:icp`,
    field_key: "icp",
    answer_type: "manual",
    status: "applied",
    confidence_delta: 8,
    analysis_blocked: false,
    answered_count: 2,
    total_count: 7,
    research_result: null,
    recalculation_status: "started",
    recalculation_data_revision: 2,
    recalculation_analysis_status: "gate2_preview_ready",
    recalculation_delta: {
      previous_revision: 1,
      new_revision: 2,
      fields_changed: ["icp"],
      core_coverage_delta: 1,
      conflicts_resolved: 0,
      conflicts_remaining: 0,
      calculations_recalculated: ["runway_months"],
      calculations_pending: ["report"],
    },
  });

  assert.equal(response.answer_type, "manual");
  assert.equal(response.confidence_delta, 8);
  assert.equal(response.recalculation_status, "started");
  assert.equal(response.recalculation_data_revision, 2);
  assert.deepEqual(response.recalculation_delta?.fields_changed, ["icp"]);
  assert.deepEqual(response.recalculation_delta?.calculations_pending, ["report"]);
  assert.equal("value" in response, false);
});

test("parses six improvement proposals and decision version changes", () => {
  const improvements = parseAdvisorImprovementsResponse({
    case_id: caseId,
    improvement_version: 6,
    proposals: Array.from({ length: 6 }, (_, index) => ({
      proposal_id: index === 0 ? proposalId : crypto.randomUUID(),
      target_area: ["POSITIONING", "MONETIZATION", "METRICS", "GTM", "RISK_REDUCTION", "INVESTOR_READINESS"][index],
      recommendation_ru: `Улучшение ${index + 1} для отчёта.`,
      rationale_ru: `Почему это важно для инвестора ${index + 1}.`,
      expected_effect_ru: `Что изменится после решения ${index + 1}.`,
      evidence_kinds: ["local_calculation", "live_inference"],
      confidence: index === 0 ? "0.72" : 0.61,
    })),
  });
  const decision = parseAdvisorImprovementDecisionResponse({
    case_id: caseId,
    proposal_id: proposalId,
    decision: "accepted",
    previous_version: 6,
    new_version: 7,
    changed_fields: ["pricing_revenue_model"],
    recalculation_status: "started",
    recalculation_data_revision: 4,
    recalculation_analysis_status: "gate2_preview_ready",
  });

  assert.equal(improvements.proposals.length, 6);
  assert.equal(improvements.proposals[0]?.confidence, 0.72);
  assert.equal(decision.previous_version, 6);
  assert.equal(decision.new_version, 7);
  assert.equal(decision.recalculation_status, "started");
  assert.equal(decision.recalculation_data_revision, 4);
});

test("rejects founder-facing advisor text that leaks hashes paths filenames prompts or MISSING", () => {
  for (const leakedText of [
    "MISSING",
    `sha256:${"a".repeat(64)}`,
    "D:\\Agents\\private\\pitch.pdf",
    "source.docx",
    "system prompt with trace token",
  ]) {
    assert.throws(
      () =>
        parseAdvisorNextQuestionResponse({
          case_id: caseId,
          status: "active",
          next_question: {
            question_id: `${caseId}:icp`,
            field_key: "icp",
            question_ru: leakedText,
            reason_ru: "Безопасная причина.",
            unlocks_ru: "Безопасный результат.",
            answer_modes: ["manual", "skip"],
            origin: "document_contradiction",
            origin_label_ru: "Противоречие в документе",
            context_ru: "Безопасный контекст.",
            answer_mode_labels_ru: {
              manual: "Ответить вручную",
              file: "Прикрепить файл",
              public_research: "Разрешить публичный поиск",
              skip: "Пропустить",
            },
          },
          answered_count: 0,
          total_count: 5,
        }),
      ApiContractError,
      leakedText,
    );
  }
});
