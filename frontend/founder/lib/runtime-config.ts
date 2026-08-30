import type { StartupCreateRequest } from "./contracts.ts";

export type FounderCaseFixtureMode = StartupCreateRequest["fixture_mode"];

export type FounderRuntimeConfig = Readonly<{
  caseFixtureMode: FounderCaseFixtureMode;
}>;

export function normalizeFounderCaseFixtureMode(
  rawMode: string | undefined,
): FounderCaseFixtureMode {
  if (rawMode === undefined || rawMode === "" || rawMode === "live") {
    return "live";
  }
  if (rawMode === "deterministic_offline") {
    return "deterministic_offline";
  }
  throw new Error(
    `Unsupported FOUNDER_CASE_FIXTURE_MODE "${rawMode}". Use "live" or "deterministic_offline".`,
  );
}

function runtimeConfigError(): Error {
  return new Error("Runtime fixture mode is unavailable");
}

export async function resolveFounderRuntimeConfig(
  fetchConfig: typeof fetch = globalThis.fetch,
): Promise<FounderRuntimeConfig> {
  const response = await fetchConfig("/api/runtime-config", { cache: "no-store" });
  if (!response.ok) {
    throw runtimeConfigError();
  }
  const payload = (await response.json()) as Partial<
    Readonly<{ caseFixtureMode: unknown }>
  >;
  if (typeof payload.caseFixtureMode !== "string") {
    throw runtimeConfigError();
  }
  return {
    caseFixtureMode: normalizeFounderCaseFixtureMode(payload.caseFixtureMode),
  };
}
