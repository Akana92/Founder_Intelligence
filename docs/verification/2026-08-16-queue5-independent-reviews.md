# Queue 5 independent review record - 2026-08-16

## Review basis

- Branch: `main`.
- Final reviewed implementation and packet-input HEAD: `20b9876526caa5e97e9226b2e05c58a436a2f586`.
- Fresh offline evidence root: `.local/queue5-final-2ec2611-20260816-04`.
- Final deterministic packets: `freeze-final-a-20b9876` and `freeze-final-b-20b9876`.
- Authoritative binder: `verification-final-20b9876/queue5-verification-summary.json`.
- Live LangSmith side evidence: `.local/queue5-live-6ba58c5-langsmith-proof-01/langsmith-trace-evidence.json`.
- Live OpenAI side evidence: `.local/queue5-live-9b9ed8e-openai-proof-03/openai-competitor-smoke-evidence.json`.
- Reviews were read-only over source and runtime artifacts. The verification records were written only after the verdicts; no reviewer changed frozen/runtime evidence or printed credential values.

## Code and security review

**Verdict: APPROVE. Findings: 0.**

The independent Queue 5 code/security lane reviewed the implementation through `2ec2611`, including the Sellable Demo packet builder, failure matrix, LangSmith exporter/privacy behavior, OpenAI smoke boundaries, PDF privacy validation, and report lineage binding.

Independent validation:

```text
targeted Queue 5 pytest -> 102 passed
Ruff on reviewed Python/tests -> PASS
strict mypy on reviewed source -> PASS
```

Confirmed boundaries:

- tracing disabled constructs no LangSmith client and emits no external export;
- enabled tracing exports only sanitized metadata, empty inputs/outputs, no attachments, and filesystem capture disabled;
- exporter outage does not break the startup workflow, and Admin/local audit remains the safe source of truth;
- OpenAI competitor smoke is exactly one bounded post-Gate-2 call with timeout, no retries, budget guard, sanitized input, and no live web research;
- frozen packet, PDF journey, LangSmith trace evidence, and OpenAI side evidence remain separate namespaces;
- no committed source hardcodes or prints live secrets.

## Runtime path security review

**Verdict: APPROVE. Findings: 0.**

The Gate D evidence-path confinement fix at `72e5856` was reviewed independently after a strict packet failure exposed a repo-relative `.local/.../runtime-evidence.json` resolution bug.

Independent validation:

```text
21 adjacent packet/path tests -> PASS before review
7 targeted path tests -> PASS in the independent review
Ruff -> PASS
strict mypy -> PASS
```

Confirmed boundaries:

- absolute evidence paths outside the owner root are rejected;
- `..` traversal is rejected;
- repo-relative evidence paths are accepted only when resolved inside the owner root;
- symlink confinement remains fail-closed.

## Visual, browser, Admin, and PDF review

**Verdict: APPROVE. No blocking findings.**

Evidence root: `.local/queue5-final-2ec2611-20260816-04/pdf-browser`.

- Desktop screenshot is `1440x1000`; mobile screenshot is `390x844`.
- Intake is PDF-only with one frozen `application/pdf`, no prompt selection, and no industry selection.
- Case `80836367-af35-4a95-86dd-8e871f47905c`, Admin run `startup-api-80836367-af35-4a95-86dd-8e871f47905c`, report id `1f87d2cd-9df7-5f6b-b0e1-3117059744ae`, revision `1`, and checksum `c103e0231581981cf852936394dc62528162eb4c4df6596ef50f6a5f3d0de7c4` are shared across browser/Admin/report evidence.
- Admin has 21 successful workflow rows with matching lineage.
- Gate 4 is approved/completed.
- Same-case JSON/HTML/PDF hashes are recorded.
- `network_external_calls=0`; one Kaspersky parser injection was blocked before egress.
- No raw document, local path, credential, prompt, or PII leak was detected in the reviewed evidence.

Non-blocking demo polish: local horizontal scrollbars remain visible in dense desktop table/card regions, but they do not block the demo path.

## Documentation review

**Verdict: APPROVE. Findings: 0.**

The packet-input docs review at `20b9876` verified the demo script, one-page capstone map, and packet hash inputs.

Independent validation:

```text
docs privacy/timing checks -> 4 passed
demo script hash -> sha256:04cdee1df2cbed46f944054ad62b7fc33dbe78b2159cf1d785893a8e32930003
capstone map hash -> sha256:2d720f6ed1ae8c8b4630e6e45bf39d9d54f5c7fa59ba668918d6dca8d5354e38
```

Confirmed boundaries:

- demo script remains within the 7-10 minute target;
- docs do not expose credential values;
- docs do not overclaim Pilot-Ready or Production-Ready;
- deterministic packet inputs match the final frozen packet.

## Final assembled acceptance review

**Verdict: APPROVE. Findings: 0.**

Final acceptance validates the updated owner boundary:

- fresh offline Gate B/C/D-A/D-B/E runs pass with deterministic/offline settings, tracing disabled, and no provider-network dependency;
- Gate D semantic determinism is recorded separately from raw runtime/eval hashes;
- strict packet pair is byte-identical with raw SHA-256 `b207df62b81c54371bc90155218ce77d7473215ed5ab9a2a77110a1262a23fc8`;
- canonical packet hash is `sha256:72861ee63d5ced4fa34e2c9e834c78e0cf275d8d1bb67f7fff30b605f2dba854`;
- PDF desktop/mobile browser/API/Admin journey passes with same-case approved JSON/HTML/PDF lineage;
- failure matrix passes with hash `sha256:15fec1331c56783845fee89152e6030bbe9b898ea78c3a078f3a31be14a0b98b`;
- full backend pytest, Ruff, strict mypy, frontend test/typecheck/lint/build evidence is present and passing;
- real sanitized LangSmith trace passes with 22 runs, 20 workflow nodes, 0 export errors, Admin health `healthy`, and privacy leak count `0`;
- bounded OpenAI competitor smoke passes with credential-present boolean `true`, Gate 2 approval before the provider boundary, exactly one call, five competitor categories, privacy leak count `0`, and budget below USD `0.25`;
- final binder has `blockers=[]` and `queue5_sellable_demo_ready=true`.

The OpenAI smoke's sanitized StartupProfile fields are `MISSING`. This is acceptable for the smoke requirement because the request boundary allows a bounded sanitized StartupProfile plus frozen competitor evidence/source summaries, and the output explicitly marks ICP overlap, differentiation, and risk as unknown instead of inventing startup-specific facts. The evidence remains a live inference test, not live web research.

## Final review decision

Independent code/security, runtime-path security, visual/PDF/Admin, documentation, and final assembled acceptance lanes: **APPROVE**.

Queue 5 / Sellable Demo is ready for the educational demo-defense boundary represented by this evidence set. Pilot-Ready and Production-Ready remain open and are not claimed.
