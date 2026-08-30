import assert from "node:assert/strict";
import test from "node:test";

import { parseProductCapabilities } from "./contracts.ts";

const liveContract = parseProductCapabilities({
  contract_version: "founder_capabilities.v1",
  delivery_profile: "sales_ready_hybrid",
  capabilities: [
    {
      key: "universal_upload",
      label: "Universal startup document upload",
      lifecycle_status: "available",
      user_selectable: false,
    },
    {
      key: "primary_startup_analysis",
      label: "Primary startup readiness analysis",
      lifecycle_status: "available",
      user_selectable: false,
    },
    {
      key: "deep_startup_analysis",
      label: "Deep startup market and evidence analysis",
      lifecycle_status: "planned",
      user_selectable: false,
    },
    {
      key: "public_comparable_analysis",
      label: "Public company comparable analysis",
      lifecycle_status: "available",
      user_selectable: false,
    },
  ],
  research_policy: "guarded_live_with_cached_fallback",
  surfaces: {
    founder_workspace: "separate_web",
    admin_console: "streamlit",
  },
  upgrade_target: {
    target: "full_platform",
    preserved_contracts: ["analytics_core", "api_v1"],
  },
  user_selectable_modes: [],
});

test("presents the connected private analysis path in readable Russian", async () => {
  const presentationModule = await import("./capability-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "capability presentation must be implemented");

  const presentation = presentationModule.presentCapabilityBoundary({
    kind: "ready",
    contract: liveContract,
  });

  assert.equal(presentation.kind, "ready");
  assert.equal(presentation.title, "Рабочая система анализа подключена");
  assert.match(presentation.detail, /приватный рабочий кейс/u);
  assert.doesNotMatch(JSON.stringify(presentation), /Live API|live-кейс|comparables|Safe Startup Ingest/u);
  assert.doesNotMatch(presentation.detail, /файлы остаются в браузере/u);
  assert.deepEqual(
    presentation.capabilities.map((item) => [item.key, item.lifecycle]),
    [
      ["universal_upload", "available"],
      ["primary_startup_analysis", "available"],
      ["deep_startup_analysis", "planned"],
      ["public_comparable_analysis", "available"],
    ],
  );
});

test("presents an unavailable API without simulated results or fixture fallback", async () => {
  const presentationModule = await import("./capability-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "capability presentation must be implemented");

  const presentation = presentationModule.presentCapabilityBoundary({
    kind: "unavailable",
  });

  assert.equal(presentation.kind, "unavailable");
  assert.equal(presentation.title, "Сервис анализа недоступен");
  assert.match(presentation.detail, /не запускаются/u);
  assert.match(presentation.detail, /не имитируются/u);
  assert.doesNotMatch(presentation.detail, /fixture|демо-данн/u);
});

test("explains the real document transit boundary before and after launch", async () => {
  const presentationModule = await import("./capability-presentation.ts").catch(
    () => null,
  );
  assert.ok(presentationModule, "capability presentation must be implemented");

  assert.match(presentationModule.founderDocumentTransitCopy, /До запуска/u);
  assert.match(
    presentationModule.founderDocumentTransitCopy,
    /отправляются в приватный рабочий кейс/u,
  );
  assert.doesNotMatch(
    presentationModule.founderDocumentTransitCopy,
    /live-кейс|Safe Startup Ingest/u,
  );
});
