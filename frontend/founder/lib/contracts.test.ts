import assert from "node:assert/strict";
import test from "node:test";

import {
  CapabilityContractError,
  parseProductCapabilities,
} from "./contracts.ts";

const validContract = {
  contract_version: "founder_capabilities.v1",
  delivery_profile: "sales_ready_hybrid",
  capabilities: [
    {
      key: "universal_upload",
      label: "Universal startup document upload",
      lifecycle_status: "planned",
      user_selectable: false,
    },
    {
      key: "primary_startup_analysis",
      label: "Primary startup readiness analysis",
      lifecycle_status: "planned",
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
} as const;

test("accepts the exact Founder capabilities v1 contract", () => {
  const parsed = parseProductCapabilities(validContract);

  assert.equal(parsed.contract_version, "founder_capabilities.v1");
  assert.equal(parsed.delivery_profile, "sales_ready_hybrid");
  assert.equal(parsed.capabilities.length, 4);
  assert.equal(parsed.capabilities[3]?.lifecycle_status, "available");
  assert.deepEqual(parsed.user_selectable_modes, []);
});

test("rejects an unknown contract discriminator", () => {
  assert.throws(
    () =>
      parseProductCapabilities({
        ...validContract,
        contract_version: "founder_capabilities.v2",
      }),
    CapabilityContractError,
  );
});

test("rejects missing or duplicated required capabilities", () => {
  assert.throws(
    () =>
      parseProductCapabilities({
        ...validContract,
        capabilities: [
          validContract.capabilities[0],
          validContract.capabilities[0],
          validContract.capabilities[2],
          validContract.capabilities[3],
        ],
      }),
    /unique required capability keys/,
  );
});

test("rejects any user-selectable product mode", () => {
  assert.throws(
    () =>
      parseProductCapabilities({
        ...validContract,
        user_selectable_modes: ["saas"],
      }),
    /user_selectable_modes/,
  );
});
