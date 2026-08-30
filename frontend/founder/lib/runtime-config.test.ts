import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  normalizeFounderCaseFixtureMode,
  resolveFounderRuntimeConfig,
} from "./runtime-config.ts";

test("normalizes only explicit founder fixture modes", () => {
  assert.equal(normalizeFounderCaseFixtureMode(undefined), "live");
  assert.equal(normalizeFounderCaseFixtureMode(""), "live");
  assert.equal(normalizeFounderCaseFixtureMode("live"), "live");
  assert.equal(
    normalizeFounderCaseFixtureMode("deterministic_offline"),
    "deterministic_offline",
  );
  assert.throws(
    () => normalizeFounderCaseFixtureMode("demo"),
    /Unsupported FOUNDER_CASE_FIXTURE_MODE/u,
  );
});

test("resolves runtime config with no-store fetch and fails closed", async () => {
  const requests: Array<Readonly<{ input: string; init: RequestInit | undefined }>> = [];
  const config = await resolveFounderRuntimeConfig(async (input, init) => {
    requests.push({ input: String(input), init });
    return Response.json({ caseFixtureMode: "deterministic_offline" });
  });

  assert.deepEqual(config, { caseFixtureMode: "deterministic_offline" });
  assert.deepEqual(requests, [
    { input: "/api/runtime-config", init: { cache: "no-store" } },
  ]);

  await assert.rejects(
    resolveFounderRuntimeConfig(async () => Response.json({}, { status: 500 })),
    /Runtime fixture mode is unavailable/u,
  );
  await assert.rejects(
    resolveFounderRuntimeConfig(async () => Response.json({ caseFixtureMode: "demo" })),
    /Unsupported FOUNDER_CASE_FIXTURE_MODE/u,
  );
});

test("runtime config route reads server env and declares no-store response headers", () => {
  const route = readFileSync(
    new URL("../app/api/runtime-config/route.ts", import.meta.url),
    "utf8",
  );

  assert.match(route, /process\.env\.FOUNDER_CASE_FIXTURE_MODE/u);
  assert.match(route, /normalizeFounderCaseFixtureMode/u);
  assert.match(route, /"Cache-Control": "private, no-cache, no-store, max-age=0, must-revalidate"/u);
  assert.match(route, /status: 500/u);
});
