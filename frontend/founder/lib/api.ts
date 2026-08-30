import {
  CapabilityContractError,
  parseProductCapabilities,
  type ProductCapabilities,
} from "./contracts";
import { proxyFounderApi } from "./startup-proxy";

export type CapabilityFetchFailureReason =
  | "api_unreachable"
  | "api_timeout"
  | "api_rejected"
  | "invalid_contract";

export class CapabilityFetchError extends Error {
  readonly reason: CapabilityFetchFailureReason;

  constructor(reason: CapabilityFetchFailureReason, message: string) {
    super(message);
    this.name = "CapabilityFetchError";
    this.reason = reason;
  }
}

export async function fetchProductCapabilities(): Promise<ProductCapabilities> {
  let response: Response;
  try {
    response = await proxyFounderApi(
      new Request("http://founder.local/api/capabilities", {
        method: "GET",
        headers: { Accept: "application/json" },
      }),
    );
  } catch {
    throw new CapabilityFetchError(
      "api_unreachable",
      "Founder API could not be reached",
    );
  }

  if (!response.ok) {
    const reason = await response
      .clone()
      .json()
      .then((body: unknown) => {
        if (
          typeof body === "object" &&
          body !== null &&
          "code" in body &&
          typeof body.code === "string"
        ) {
          return body.code;
        }
        return "api_rejected";
      })
      .catch(() => "api_rejected");

    throw new CapabilityFetchError(
      reason === "api_timeout" ? "api_timeout" : "api_rejected",
      `Founder API returned ${response.status}`,
    );
  }

  try {
    return parseProductCapabilities(await response.json());
  } catch (error) {
    if (error instanceof CapabilityContractError) {
      throw new CapabilityFetchError("invalid_contract", error.message);
    }
    throw new CapabilityFetchError(
      "invalid_contract",
      "Founder API response was not valid JSON",
    );
  }
}
