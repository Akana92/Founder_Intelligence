# Queue 5 Sellable Demo verification — 2026-08-16

## Scope and current decision

- Branch: `main`.
- Fresh Gates, browser journey, and failure-matrix evidence commit: `2ec2611e6ed3033b39187ec4709dd5bc31538216`.
- Gate D evidence-path confinement fix and final full toolchain commit: `72e5856`.
- Packet-input documentation commit: `20b9876526caa5e97e9226b2e05c58a436a2f586`.
- Fresh offline evidence root: `.local/queue5-final-2ec2611-20260816-04` (runtime-only, not committed).
- Deterministic packets: `freeze-final-a-20b9876` and `freeze-final-b-20b9876` under that root.
- Authoritative binder: `verification-final-20b9876/queue5-verification-summary.json` under that root.
- Live LangSmith side evidence: `.local/queue5-live-6ba58c5-langsmith-proof-01/langsmith-trace-evidence.json`.
- Live OpenAI competitor side evidence: `.local/queue5-live-9b9ed8e-openai-proof-03/openai-competitor-smoke-evidence.json`.
- Queue 1–4 remains frozen/offline and was not rewritten.

Current decision: **Queue 5 / Sellable Demo is ready for the educational demo-defense boundary represented by this evidence set.** The final independent acceptance review approved the assembled record with findings `0`. Pilot-Ready and Production-Ready are outside this decision and remain open.

Offline packet determinism, live LangSmith trace evidence, and live OpenAI competitor evidence remain separate namespaces. Neither live side proof changes canonical offline Gate D/E semantics or the frozen packet hash.

## Lane status

| Lane | Evidence | Status |
| --- | --- | --- |
| Offline Gate B | `.local/queue5-final-2ec2611-20260816-04/gate-b/eval-result.json` | PASS |
| Offline Gate C | `.local/queue5-final-2ec2611-20260816-04/gate-c/eval-result.json` | PASS |
| Offline Gate D-A | `.local/queue5-final-2ec2611-20260816-04/gate-d-a/eval-result.json` | PASS |
| Offline Gate D-B | `.local/queue5-final-2ec2611-20260816-04/gate-d-b/eval-result.json` | PASS |
| Offline Gate E | `.local/queue5-final-2ec2611-20260816-04/gate-e/eval-result.json` | PASS |
| Real PDF browser/API/Admin journey | `.local/queue5-final-2ec2611-20260816-04/pdf-browser/browser-evidence.json` | PASS |
| Failure matrix | `.local/queue5-final-2ec2611-20260816-04/failure-matrix/failure-matrix.json` | PASS |
| Real sanitized LangSmith trace | `.local/queue5-live-6ba58c5-langsmith-proof-01/langsmith-trace-evidence.json` | PASS |
| Bounded OpenAI competitor smoke | `.local/queue5-live-9b9ed8e-openai-proof-03/openai-competitor-smoke-evidence.json` | PASS |
| Frozen packet pair | `freeze-final-a-20b9876` and `freeze-final-b-20b9876` | PASS; byte-identical |
| Final binder | `verification-final-20b9876/queue5-verification-summary.json` | PASS; no blockers |

## Fresh offline Gates B/C/D/E

All five Gate runs were produced with OpenAI keys blank for the gate processes, LangSmith tracing disabled, offline model/data settings enabled, and no allowed external provider calls.

| Gate | Verified result |
| --- | --- |
| Gate B | Pass; privacy leak count `0`; numerical accuracy, schema, trace, report, retrieval, and exporter-outage checks pass. |
| Gate C | Pass; privacy leak count `0`; restart/profile determinism passes; denied Gate 2 external calls `0`; required document formats are covered. |
| Gate D-A | Pass; privacy leak count `0`; denied Gate 2 external calls `0`; startup analysis/report/trace assertions pass. |
| Gate D-B | Pass; privacy leak count `0`; denied Gate 2 external calls `0`; startup analysis/report/trace assertions pass. |
| Gate E | Pass; public/startup compatibility, checkpoint recovery, sanitized repository, PDF fallback, and shared-schema checks pass. |

Gate D semantic equivalence is `true` in the strict packet. Raw D-A/D-B eval and runtime hashes are recorded separately and may differ because they include runtime metadata; they are not used as the semantic-determinism decision.

## Real PDF desktop/mobile browser/API journey

Evidence root: `.local/queue5-final-2ec2611-20260816-04/pdf-browser`.

- Browser schema: `founder_browser_smoke_evidence@1`.
- Case: `80836367-af35-4a95-86dd-8e871f47905c`.
- Run: `startup-api-80836367-af35-4a95-86dd-8e871f47905c`.
- Intake: exactly one frozen `application/pdf`, `1523` bytes, SHA-256 `0312d8f0bf1055b2fd6d555f5686bdf5de319d7f4e27788dfff2d71dc927b0d5`.
- Intake mode: `pdf_upload_only`; prompt selection and industry selection are both `false`.
- Journey: primary profile -> Gate 2 -> deep analysis -> metrics/readiness -> five competitor categories and TAM/SAM/SOM evidence/unknowns -> contradictions/questions -> GTM/action plan -> Gate 4 -> same-case JSON/HTML/PDF -> Admin trace.
- Gate 4: approved/completed.
- Desktop: `1440x1000`; mobile: `390x844`.
- Report id: `1f87d2cd-9df7-5f6b-b0e1-3117059744ae`; revision `1`; checksum `c103e0231581981cf852936394dc62528162eb4c4df6596ef50f6a5f3d0de7c4`.
- JSON hash: `sha256:8ed4336db9ec2dbcf3327e99c1634dc8abac7a2e21760b465eae875a69a9a87b`.
- HTML hash: `sha256:8d5afe942e276ff4e4774f110dcfeb9a6cdbc48790e8a21561986f8148af00af`.
- PDF hash: `sha256:61bdbc3362c879ee4f936f639d04ca1887232235eac31b6e3633a07ffcb39d8d`.
- Admin trace: 21 successful workflow rows with matching case/run/report lineage.
- Network proof: `network_external_calls=0`; one Kaspersky parser injection was blocked before egress.
- Privacy evidence passes with no raw document, path, credential, prompt, or PII leak.

Independent visual review found no blocker. Desktop contains local table/card horizontal scrollbars but no critical global overflow; mobile clearly shows PDF-only intake and the selected PDF fixture.

## Real sanitized LangSmith trace

Evidence: `.local/queue5-live-6ba58c5-langsmith-proof-01/langsmith-trace-evidence.json`.

- Schema/status: `langsmith_trace_evidence@1` / `pass`.
- Credential presence boolean: `true`; no value is recorded or printed.
- Live requested/attempted/succeeded: `true/true/true`.
- Real startup workflow: 22 exported runs, 20 workflow nodes, 2 flushes, 0 export errors.
- Case: `00000000-0000-0000-0000-000000000951`.
- Run: `queue5-langsmith-run-e311d314abcd4b1c83eb0c5cc8eb8dab`.
- Admin health: `healthy`, provider `langsmith`, local audit remains the fallback/source of truth.
- Report lineage: id `50e920f4-7411-59a2-ad6a-111c113006a8`, revision `1`, checksum `55054d8ae6344ebb17ef51b6d41cdd56327c4cbbe4759a20e0ec11ef357eac29`.
- Privacy: attachments absent, inputs/outputs empty, filesystem capture disabled, unsafe capture rejected, leak count `0`.
- Evidence-owned semantic hash: `sha256:25e2940b0bb88c009751e85d17fd25435f71627c26f2d82f9e37d56db6dd4c59`.
- Binder-bound semantic hash: `sha256:9de3799b902836135d99859250474076b2fa4d8852b0ccb28fde54ed2dd3a33a`.
- Raw evidence file hash: `sha256:3cb0e318fca32c3e6f9feab5b2bab9c0e84c4ea5b8bb0ce8b65fdd521fe278d6`.

Tracing-disabled coverage proves that no client is constructed and no external export occurs. Exporter-outage coverage proves the workflow remains successful, local audit remains authoritative, and Admin exposes the sanitized exporter health state. Exported metadata excludes raw PDF/document text, filenames, local paths, prompts, chain-of-thought, PII, attachments, and secrets.

## Bounded OpenAI competitor smoke

Evidence: `.local/queue5-live-9b9ed8e-openai-proof-03/openai-competitor-smoke-evidence.json`.

- Schema/status: `openai_competitor_smoke_evidence@1` / `pass`.
- Credential presence boolean: `true`; no value is recorded or printed.
- Gate 2 was approved before the provider boundary.
- Live requested/attempted/succeeded: `true/true/true`.
- Exactly one provider call; timeout `20s`; retries `0`.
- Model configured for the smoke: `gpt-5.6-luna`.
- Output limit: `1200` tokens. The earlier `600`-token attempt produced truncated JSON; this was a response-length failure, not a bad key, token, or unsupported model.
- Usage: 1231 input, 937 output, 2168 total tokens.
- Five structured categories returned: direct, indirect, substitute, do-nothing, and potential entrant.
- Labels: `live_inference` and `not_live_web_research`.
- Input boundary: sanitized bounded StartupProfile fields plus existing frozen competitor evidence/source summaries; no raw PDF and no live web research.
- Privacy leak count: `0`; unsafe payload rejection and request/response validation pass.
- Budget guard: maximum USD `0.25`; reserved USD `0.05`; conservative configured worst case USD `0.017`.
- The committed budget guard deliberately prices Luna at the older/conservative USD `1.00` input and USD `6.00` output per million tokens, producing a conservative observed estimate of USD `0.006853`. Current official OpenAI documentation lists USD `0.20` input and USD `1.20` output per million tokens, which puts the same 1231/937-token call at approximately USD `0.0013706`; both figures remain far below the USD `0.25` cap.
- Evidence-owned semantic hash: `sha256:3fb3e0b4ae8a6c68218e1b5128cc1ee749c89074687fc6c3003e0e36265bc2a1`.
- Binder-bound semantic hash: `sha256:ff7f26afa5675b2a1651161c6ef382ede5441341addc3e4992d4fddb3fa7fcef`.
- Raw evidence file hash: `sha256:fad008d76ceea63bd1b16269fc2bb82bef2bf3d1e2d4fc5bf849ffcef5b6356b`.

The evidence schema intentionally does not claim that the model id or price is returned by OpenAI. The model id and conservative budget price come from local bounded-smoke configuration; the current comparison price is sourced separately from official OpenAI documentation. No SEC/Yahoo/GDELT/news/web call was made.

## Failure matrix

Evidence: `.local/queue5-final-2ec2611-20260816-04/failure-matrix/failure-matrix.json`.

- Schema: `queue5_failure_matrix@1`.
- Commit: `2ec2611e6ed3033b39187ec4709dd5bc31538216`.
- Result: `matrix_passed=true`, `fail_reasons=[]`, `offline_no_live_calls=true`.
- Command: 12 named proof tests, exit `0`, no timeout, timeout boundary `300s`.
- Matrix hash: `sha256:15fec1331c56783845fee89152e6030bbe9b898ea78c3a078f3a31be14a0b98b`.
- Covered defenses: missing provider key, external-source outage, typed retry, budget exhaustion and restart, renderer fallback, checkpoint restart/privacy, report/trace lineage, and exporter fallback privacy.
- The verifier recomputes the matrix hash and rejects missing, failed, timed-out, or self-declared rows/supporting validations.

## Full toolchain

Evidence root: `.local/queue5-final-2ec2611-20260816-04/toolchain-final-72e5856`.

| Check | Result |
| --- | --- |
| Full backend pytest | PASS: `1339 passed, 1 skipped in 134.21s`; the skip is the expected Windows symlink-privilege case (`WinError 1314`). |
| Ruff | PASS: `All checks passed!` |
| Strict mypy | PASS: `Success: no issues found in 227 source files` |
| Frontend tests | PASS: 104 aggregate tests |
| Frontend typecheck before build | PASS |
| Frontend lint | PASS |
| Frontend production build | PASS outside the restricted sandbox; the initial sandbox attempt failed only with Windows `spawn EPERM`. Next 16.3 compilation, TypeScript, static generation, and direction-contract verification completed. |
| Frontend typecheck after build | PASS |

`frontend/founder/next-env.d.ts` remains canonical and clean after verification.

## Frozen packet determinism

Evidence:

- `.local/queue5-final-2ec2611-20260816-04/freeze-final-a-20b9876/sellable-demo-freeze-packet.json`
- `.local/queue5-final-2ec2611-20260816-04/freeze-final-b-20b9876/sellable-demo-freeze-packet.json`

Both fail-closed output roots produced `sellable_demo_freeze_packet@1` with:

- `sellable_demo_passed=true` and `fail_reasons=[]`;
- Gate B/C/D-A/D-B/E all `pass`;
- Gate D semantic equivalence `true`, separately from raw hashes;
- privacy, desktop `1440x1000`, mobile `390x844`, and same-case approved JSON/HTML/PDF lineage passing;
- approved report lineage policy `required`;
- canonical packet hash `sha256:72861ee63d5ced4fa34e2c9e834c78e0cf275d8d1bb67f7fff30b605f2dba854`;
- byte-identical raw packet SHA-256 `b207df62b81c54371bc90155218ce77d7473215ed5ab9a2a77110a1262a23fc8`;
- identical packet size `3947` bytes;
- demo script hash `sha256:04cdee1df2cbed46f944054ad62b7fc33dbe78b2159cf1d785893a8e32930003`;
- capstone map hash `sha256:2d720f6ed1ae8c8b4630e6e45bf39d9d54f5c7fa59ba668918d6dca8d5354e38`.

The packet keeps `live_provider_smoke_status=deferred_by_policy` inside the deterministic offline namespace. Completed LangSmith and OpenAI live proofs are side evidence bound only by the final verifier.

## Authoritative final binder

Evidence: `.local/queue5-final-2ec2611-20260816-04/verification-final-20b9876/queue5-verification-summary.json`.

- Exit code: `0`.
- Blockers: `[]`.
- `failure_matrix_ready=true`.
- `frozen_packet_ready=true`.
- `langsmith_trace_ready=true`.
- `openai_competitor_smoke_ready=true`.
- `pdf_journey_ready=true`.
- `queue5_sellable_demo_ready=true`.
- Complete semantic summary hash: `sha256:e8d3d7f4dbb9517f79dba7c56a73f7054fd74c192181f39a1d4f71ad458883cd`.
- Bound PDF journey semantic hash: `sha256:f83764af243b64b8515c62ef4e82cc4fdf5d51d44662e25ab200479fd802555b`.

Raw bound file hashes:

- frozen packet: `sha256:b207df62b81c54371bc90155218ce77d7473215ed5ab9a2a77110a1262a23fc8`;
- browser evidence: `sha256:627af9ce68e7cdbe4ad95775c8a684a51b16b46542432b90b4c3e7fb4c0696ef`;
- LangSmith evidence: `sha256:3cb0e318fca32c3e6f9feab5b2bab9c0e84c4ea5b8bb0ce8b65fdd521fe278d6`;
- OpenAI evidence: `sha256:fad008d76ceea63bd1b16269fc2bb82bef2bf3d1e2d4fc5bf849ffcef5b6356b`.

## Independent review status

- Queue 5 code/security review at `2ec2611`: APPROVE, findings `0`; 102 targeted tests passed.
- Gate D runtime-path confinement review at `72e5856`: APPROVE, findings `0`; targeted tests, Ruff, strict mypy, and diff checks passed.
- Packet-input docs review at `20b9876`: APPROVE, no blockers.
- Desktop/mobile browser visual review: APPROVE, no visual blocker.
- Final assembled acceptance and verification-record review: APPROVE, findings `0`; recorded in `docs/verification/2026-08-16-queue5-independent-reviews.md`.
- The OpenAI smoke's sanitized StartupProfile fields are `MISSING`. This is not a blocker: the smoke requirement allows bounded sanitized profile input plus frozen competitor evidence/source summaries, and the output explicitly marks ICP overlap, differentiation, and comparative risk as unknown rather than inventing startup-specific facts.

## Decision boundary

Fresh offline Gates B/C/D-A/D-B/E, PDF desktop/mobile browser/API/Admin journey, sanitized LangSmith trace, bounded OpenAI competitor smoke, failure matrix, full backend/frontend toolchain, deterministic packet pair, authoritative binder, and independent assembled acceptance review: **PASS**.

Queue 5 / Sellable Demo is ready for the educational demo-defense boundary represented by this evidence set. Pilot-Ready and Production-Ready remain open and are not claimed.
