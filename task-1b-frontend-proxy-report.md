# Task 1B frontend proxy report

## Scope

- Implemented strict Founder startup DTO validators in `frontend/founder/lib/contracts.ts`.
- Added framework-independent same-origin proxy helper in `frontend/founder/lib/startup-proxy.ts`.
- Added thin Next route handlers for all required `/api/startup/**` routes.
- Routed the existing capabilities route through the same proxy boundary while preserving capability validation.
- Preserved backend files, temp/log/output directories, and unrelated worktree changes.

## RED evidence

- `node --experimental-strip-types frontend/founder/lib/startup-contracts.test.ts` failed before production edits with:
  - `SyntaxError: The requested module './contracts.ts' does not provide an export named 'ApiContractError'`
- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` failed before production edits with:
  - `Error [ERR_MODULE_NOT_FOUND]: Cannot find module ... frontend/founder/lib/startup-proxy.ts`
- `npm --prefix frontend/founder run test` and `node --test` initially hit sandbox `spawn EPERM`; direct raw test-file execution was used to capture feature RED failures.

## GREEN evidence

- `npm --prefix frontend/founder run test` -> pass:
  - contracts: 4/4
  - startup contracts: 2/2
  - startup proxy: 7/7
  - navigation: 1/1
  - upload: 2/2
- `npm --prefix frontend/founder run lint` -> exit 0.
- `npm --prefix frontend/founder run typecheck` -> exit 0.
- `npm --prefix frontend/founder run build` -> exit 0 under escalation after sandbox `spawn EPERM`; Next compiled and listed all startup routes as dynamic.

## Sensitive-pattern checks

- `rg -n "127\\.0\\.0\\.1:8000|FOUNDER_API_BASE_URL|authorization|cookie|next/server" frontend\\founder\\app frontend\\founder\\components frontend\\founder\\lib -g "*.ts" -g "*.tsx"`:
  - `127.0.0.1:8000` and `FOUNDER_API_BASE_URL` appear only in the server-side proxy helper and raw proxy tests.
  - `authorization` and `cookie` appear only in raw proxy tests and header-stripping assertions.
  - `next/server` appears only in `app/api/capabilities/route.ts`.
- `rg -n "next/server" frontend\\founder\\lib -g "*.ts"` -> no raw helper module imports `next/server`.

## Notes

- The proxy rejects unsafe route roots, decoded or encoded traversal, backslashes, and unknown startup paths before building the upstream URL.
- Forwarded request headers are limited to `accept`, non-multipart `content-type`, and normalized `x-request-id`.
- Cookies, authorization, host, origin, forwarded headers, upstream error bodies, stack traces, paths, and unsafe response headers are not forwarded to the browser.

## Review round 1 fix

### RED evidence

- `node --experimental-strip-types frontend/founder/lib/startup-contracts.test.ts` failed after adding the `case_status` regression:
  - `Missing expected exception` for non-canonical `case_status: "analysis"`.
- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` failed after adding encoded slash route-confusion regressions:
  - `Missing expected exception` for `%2F`/`%252F` dynamic segment confusion.
- The new upstream typed 404/409 preservation regression passed before production edits; no production behavior change was needed for that item.

### GREEN evidence

- `node --experimental-strip-types frontend/founder/lib/startup-contracts.test.ts` -> 2/2 pass.
- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` -> 8/8 pass.
- `npm --prefix frontend/founder run test` -> pass, 17 tests.
- `npm --prefix frontend/founder run lint` -> exit 0.
- `npm --prefix frontend/founder run typecheck` -> exit 0.
- `npm --prefix frontend/founder run build` -> exit 0 under escalation after sandbox `spawn EPERM`; Next compiled and listed all startup routes as dynamic.
- Sensitive scan findings remained constrained to server proxy/test code; `frontend/founder/lib` still has no `next/server` import.

## Review round 2 fix

### RED evidence

- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` failed after adding the complete backend startup error taxonomy table:
  - `invalid_fixture_mode`
  - `502 !== 422`

### GREEN evidence

- Added `request_validation_error`, `invalid_fixture_mode`, and `gate2_resume_failed` to the TypeScript `ApiErrorCode` union and runtime `apiErrorCodes` allowlist.
- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` -> 9/9 pass, including all backend-emitted startup codes preserving original status and exact `{code, message}` body.
- `npm --prefix frontend/founder run test` -> pass, 18 tests.
- `npm --prefix frontend/founder run lint` -> exit 0.
- `npm --prefix frontend/founder run typecheck` -> exit 0.
- `npm --prefix frontend/founder run build` -> exit 0 under escalation after sandbox `spawn EPERM`; Next compiled and listed all startup routes as dynamic.
- Sensitive scan remained constrained to server proxy/test code and the existing capabilities route; `frontend/founder/lib` still has no `next/server` import.

## Review round 3 fix

### RED evidence

- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` failed after adding the path-only helper contract regressions:
  - absolute `https://.../api/startup/...` input did not throw.

### GREEN evidence

- `mapSameOriginStartupPath` now rejects non-path and protocol-relative inputs before URL parsing.
- `node --experimental-strip-types frontend/founder/lib/startup-proxy.test.ts` -> 9/9 pass, preserving valid same-origin path mapping and all prior proxy regressions.
- `npm --prefix frontend/founder run test` -> pass, 18 tests.
- `npm --prefix frontend/founder run lint` -> exit 0.
- `npm --prefix frontend/founder run typecheck` -> exit 0.
- `npm --prefix frontend/founder run build` -> exit 0 under escalation after sandbox `spawn EPERM`; Next compiled and listed all startup routes as dynamic.
- Sensitive scan remained constrained to server proxy/test code and the existing capabilities route; `frontend/founder/lib` still has no `next/server` import.
