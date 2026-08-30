import { NextResponse } from "next/server";

import { CapabilityFetchError, fetchProductCapabilities } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const contract = await fetchProductCapabilities();
    return NextResponse.json(contract, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const reason =
      error instanceof CapabilityFetchError
        ? error.reason
        : "contract_unavailable";

    return NextResponse.json(
      {
        status: "unavailable",
        reason,
        message:
          "Founder API недоступен. Интерфейс остаётся в безопасном демонстрационном режиме.",
      },
      {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
