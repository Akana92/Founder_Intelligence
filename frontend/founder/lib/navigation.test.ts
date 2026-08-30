import assert from "node:assert/strict";
import test from "node:test";

import {
  adminConsoleLinkForCase,
  adminRedirectUrl,
  founderUrlForCase,
  surfaceLinkFor,
} from "./navigation.ts";

test("keeps founder comparables inside the product and the operator console separate", () => {
  assert.deepEqual(surfaceLinkFor("public_comparables"), {
    href: "/comparables",
    external: false,
  });
  assert.deepEqual(surfaceLinkFor("admin_console"), {
    href: "/admin",
    external: false,
  });
});

test("keeps the active founder case in the URL while preserving other query params", () => {
  assert.equal(
    founderUrlForCase(
      "http://127.0.0.1:3000/?view=metrics&utm=demo",
      "11111111-1111-4111-8111-111111111111",
    ),
    "/?view=metrics&utm=demo&caseId=11111111-1111-4111-8111-111111111111",
  );

  assert.equal(
    founderUrlForCase(
      "http://127.0.0.1:3000/?caseId=old&view=market",
      "22222222-2222-4222-8222-222222222222",
    ),
    "/?caseId=22222222-2222-4222-8222-222222222222&view=market",
  );
});

test("links the founder case to the admin console with the same case id", () => {
  assert.deepEqual(adminConsoleLinkForCase("11111111-1111-4111-8111-111111111111"), {
    href: "/admin?caseId=11111111-1111-4111-8111-111111111111",
    external: false,
  });
});

test("preserves the selected case when redirecting to the Streamlit admin", () => {
  assert.equal(
    adminRedirectUrl(
      "http://127.0.0.1:8501/",
      { caseId: "11111111-1111-4111-8111-111111111111" },
    ),
    "http://127.0.0.1:8501/?caseId=11111111-1111-4111-8111-111111111111",
  );
  assert.equal(
    adminRedirectUrl(
      "http://127.0.0.1:8501/?mode=debug",
      {
        caseId: [
          "33333333-3333-4333-8333-333333333333",
          "44444444-4444-4444-8444-444444444444",
        ],
        view: "ignored",
      },
    ),
    "http://127.0.0.1:8501/?mode=debug&caseId=33333333-3333-4333-8333-333333333333",
  );
});
