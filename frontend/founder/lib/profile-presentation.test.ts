import assert from "node:assert/strict";
import test from "node:test";

type StartupProfileField = Readonly<{
  status: "source_fact" | "inference" | "insufficient_data" | "contradiction";
  values: readonly string[];
  confidence: string;
  evidence_refs: readonly Readonly<{
    evidence_id: string;
    artifact_id: string;
    artifact_hash: string;
    locator_hash: string;
    field_name: string;
    confidence: string;
  }>[];
  dependency_refs: readonly string[];
  reason_code: string | null;
  contradiction_ids: readonly string[];
}>;

type StartupProfileResponse = Readonly<{
  case_id: string;
  profile_id: string;
  profile_hash: string;
  data_revision: number;
  analysis_stage: "primary" | "enriched";
  parent_profile_id: string | null;
  fields: Readonly<Record<string, StartupProfileField>>;
  gaps: readonly string[];
  contradictions: readonly string[];
  parse_inventory: Readonly<{
    source_hashes: Readonly<Record<string, string>>;
    parse_outcomes: Readonly<Record<string, string>>;
  }>;
}>;

const startupProfile: StartupProfileResponse = {
  case_id: "case-founder-001",
  profile_id: "profile-founder-001",
  profile_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  data_revision: 2,
  analysis_stage: "enriched",
  parent_profile_id: "profile-founder-primary-001",
  fields: {
    startup_name: {
      status: "source_fact",
      values: ["FounderCo"],
      confidence: "0.95",
      evidence_refs: [
        {
          evidence_id: "evidence-startup-name-001",
          artifact_id: "artifact-deck-001",
          artifact_hash:
            "sha256:1111111111111111111111111111111111111111111111111111111111111111",
          locator_hash:
            "sha256:2222222222222222222222222222222222222222222222222222222222222222",
          field_name: "startup_name",
          confidence: "0.95",
        },
      ],
      dependency_refs: [],
      reason_code: null,
      contradiction_ids: [],
    },
    icp: {
      status: "insufficient_data",
      values: [],
      confidence: "0",
      evidence_refs: [],
      dependency_refs: [],
      reason_code: "missing_icp",
      contradiction_ids: [],
    },
    traction: {
      status: "contradiction",
      values: ["ARR $1.2M", "ARR $900K"],
      confidence: "0.70",
      evidence_refs: [],
      dependency_refs: [],
      reason_code: "conflicting_arr_claims",
      contradiction_ids: ["contradiction-arr-001"],
    },
    business_model: {
      status: "inference",
      values: ["B2B SaaS"],
      confidence: "0.82",
      evidence_refs: [],
      dependency_refs: ["evidence-startup-name-001"],
      reason_code: "model_inferred_from_deck",
      contradiction_ids: [],
    },
  },
  gaps: ["icp"],
  contradictions: ["contradiction-arr-001"],
  parse_inventory: {
    source_hashes: {
      "doc-0001":
        "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    },
    parse_outcomes: { "doc-0001": "parsed" },
  },
};

test("projects canonical startup profile fields into evidence-aware founder cards", async () => {
  const presentationModule = await import("./profile-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "startup profile presentation must be implemented");

  const presentation = presentationModule.buildStartupProfilePresentation(
    startupProfile,
  );

  assert.equal(presentation.stageLabel, "Углублённый профиль");
  assert.equal(presentation.snapshotLabel, "Версия данных 2");
  assert.deepEqual(
    presentation.cards.map((card: { field: string; valueLabel: string; status: string }) => [
      card.field,
      card.valueLabel,
      card.status,
    ]),
    [
      ["startup_name", "FounderCo", "source_fact"],
      ["icp", "Не указано", "insufficient_data"],
      ["traction", "ARR $1.2M · ARR $900K", "contradiction"],
      ["business_model", "B2B SaaS", "inference"],
    ],
  );
  assert.deepEqual(presentation.cards[0]?.evidenceIds, [
    "evidence-startup-name-001",
  ]);
  assert.equal(presentation.gapCount, 1);
  assert.equal(presentation.contradictionCount, 1);
});

test("uses Russian-first guidance for founder metrics and growth terms", async () => {
  const presentationModule = await import("./profile-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "startup profile presentation must be implemented");
  const missingField = {
    status: "insufficient_data" as const,
    values: [],
    confidence: "0",
    evidence_refs: [],
    dependency_refs: [],
    reason_code: null,
    contradiction_ids: [],
  };
  const presentation = presentationModule.buildStartupProfilePresentation({
    ...startupProfile,
    fields: {
      pricing_revenue_model: missingField,
      traction: missingField,
      weaknesses: missingField,
      metric_pack_candidates: missingField,
    },
  });
  const readable = JSON.stringify(
    presentation.cards.map((card: { labelRu: string; valueLabelRu: string }) => ({
      label: card.labelRu,
      value: card.valueLabelRu,
    })),
  );

  assert.match(readable, /Сигналы спроса/u);
  assert.match(readable, /ежемесячную и годовую регулярную выручку \(MRR\/ARR\)/u);
  assert.match(readable, /валовую маржу/u);
  assert.match(readable, /отток клиентов/u);
  assert.match(readable, /темп расходов/u);
  assert.match(readable, /запас времени/u);
  assert.doesNotMatch(readable, /gross margin|go-to-market|\bchurn\b|\bretention\b|\bburn\b|\brunway\b|\btraction\b/iu);
});

test("summarizes profile coverage and evidence inventory without averaging away gaps", async () => {
  const presentationModule = await import("./profile-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "startup profile presentation must be implemented");

  const presentation = presentationModule.buildStartupProfilePresentation(
    startupProfile,
  );

  assert.deepEqual(presentation.coverage, {
    totalFieldCount: 4,
    coveredFieldCount: 3,
    sourceFactFieldCount: 1,
    inferredFieldCount: 1,
    contradictionFieldCount: 1,
    missingFieldCount: 1,
    coveragePercent: 75,
    evidenceBackedPercent: 25,
  });
  assert.equal(presentation.sourceCount, 1);
  assert.equal(presentation.parsedSourceCount, 1);
});

test("keeps profile presentation founder-safe without invented scores or private raw material", async () => {
  const presentationModule = await import("./profile-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "startup profile presentation must be implemented");

  const presentation = presentationModule.buildStartupProfilePresentation(
    startupProfile,
  );
  const serialized = JSON.stringify(presentation);

  assert.equal("score" in presentation, false);
  assert.doesNotMatch(serialized, /raw|filename|path|prompt|excerpt|token/iu);
  assert.doesNotMatch(serialized, /Founder Pitch Secret\.pdf/u);
  assert.match(serialized, /profile-founder-001/u);
  assert.match(serialized, /sha256:aaaaaaaa/u);
});

test("adds Russian founder-facing labels, next actions, and hides missing codes from primary cards", async () => {
  const presentationModule = await import("./profile-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "startup profile presentation must be implemented");

  const presentation = presentationModule.buildStartupProfilePresentation(
    startupProfile,
  );
  const icpCard = presentation.cards.find(
    (card: { field: string }) => card.field === "icp",
  );
  const tractionCard = presentation.cards.find(
    (card: { field: string }) => card.field === "traction",
  );

  assert.equal(presentation.stageLabelRu, "Углублённый профиль");
  assert.equal(icpCard?.labelRu, "Идеальный клиент");
  assert.equal(
    icpCard?.valueLabelRu,
    "Пока нет подтверждённого сегмента. Добавьте целевой сегмент (ICP), бюджет владельца и пример покупателя, и я уточню позиционирование.",
  );
  assert.equal(
    tractionCard?.nextActionRu,
    "Сверьте противоречивые цифры и оставьте одну версию с датой, источником и определением метрики.",
  );
  assert.equal(icpCard?.technicalReasonCode, "missing_icp");
  assert.doesNotMatch(String(icpCard?.valueLabelRu), /\bMissing\b/u);
});
