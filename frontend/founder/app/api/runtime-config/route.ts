import { NextResponse } from "next/server";

import { normalizeFounderCaseFixtureMode } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

const noStoreHeaders = {
  "Cache-Control": "private, no-cache, no-store, max-age=0, must-revalidate",
} as const;

export async function GET(): Promise<NextResponse> {
  try {
    return NextResponse.json(
      {
        caseFixtureMode: normalizeFounderCaseFixtureMode(
          process.env.FOUNDER_CASE_FIXTURE_MODE,
        ),
      },
      { headers: noStoreHeaders },
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Runtime fixture mode is invalid";
    return NextResponse.json(
      { error: message },
      { headers: noStoreHeaders, status: 500 },
    );
  }
}
