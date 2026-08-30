# Queue 0 — verified offline baseline

**Verified:** 2026-08-13  
**Branch:** `codex/founder-sales-ready-hybrid`  
**Gate C revision:** `71c6b3741a5a4b9e596aa6db46d0b9f6527c5322`  
**Policy:** all checks below ran with OpenAI keys blank, tracing disabled, and no live provider call.

## Verdict

Queue 0 is GREEN. The repository has a reproducible offline Gate C, Gate B remains GREEN, the focused startup backend baseline is GREEN, backend static gates are GREEN, and every Founder frontend gate is GREEN.

This baseline does not claim that the complete startup product is finished. In particular, the active startup parser currently handles PDF, DOCX, PNG, and JPEG. CSV/XLSX are accepted and have a separately verified parser component, but they are not yet wired into `StartupParsingService`; ZIP is safely expanded by ingest rather than parsed as a document. Closing that end-to-end gap belongs to Queue 1.

## Canonical Gate C

Command:

```powershell
.\scripts\run_stage1b_gate_c.ps1 -OutputDir output\gate-c\startup_secure_ingest_v1-final
```

Result:

- process exit: `0`
- `gate_c_passed`: `true`
- `gate_b_passed`: `true`
- behavior checks: `6/6`, all return code `0`
- `privacy_leak_count`: `0`
- `denied_gate2_external_calls`: `0`
- fail reasons: `0`
- offline latency: `0.39115` minutes
- both OpenAI keys blank: `true`
- LangSmith, LangChain v1/v2 tracing disabled: `true`
- Hugging Face and Transformers offline: `true`
- secret-pattern scan of Gate C JSON: `0` matches

Artifact:

- path: `output/gate-c/startup_secure_ingest_v1-final/eval-result.json`
- bytes: `5350`
- SHA-256: `bd08cd6adf8697a3685ac61bca54a35bc4795b15ac84a131284847924497b9a2`

The artifact stores hashes and byte counts for non-empty command streams rather than raw stdout/stderr.

### Gate B regression inside Gate C

- `gate_b_passed`: `true`
- privacy leaks: `0`
- trace completeness: `1.0`
- report completeness: `1.0`
- schema validity: `1.0`
- budget violations: `0`
- artifact SHA-256: `02863deb637b229e3b5422bc434bfce7e78702667ca5086ea73ff000b95b53d2`

## Focused startup backend

### API/coordinator/offline fixture batch

```powershell
.venv\Scripts\pytest.exe -p no:cacheprovider `
  tests/unit/application/test_startup_case_coordinator.py `
  tests/api/test_startup_api.py `
  tests/smoke/test_startup_offline_fixture.py `
  tests/evaluation/test_startup_demo_fixture.py
```

Result: `36 passed in 2.82s`.

### Graph/report/provider/budget batch

```powershell
.venv\Scripts\pytest.exe -p no:cacheprovider `
  tests/graph/test_startup_workflow.py `
  tests/unit/reporting/test_startup_report_snapshot.py `
  tests/unit/reporting/test_report_service_orchestration.py `
  tests/e2e/test_startup_report.py `
  tests/unit/llm/test_startup_openai_provider.py `
  tests/unit/llm/test_startup_openai_provider_factory.py `
  tests/unit/llm/test_budget_guard.py `
  tests/unit/llm/test_model_fallback.py
```

Result: `81 passed in 15.84s`.

Two reproducibility defects were found and fixed before recording the pass:

1. Console-script pytest did not reliably put the repository root on `sys.path`; `pythonpath = ["."]` now makes cross-test fixture imports deterministic.
2. Graph tests manually entered `SqliteSaver` contexts without closing them; an autouse teardown now closes every registered checkpoint context, eliminating the Windows file-handle leak.

## Static backend gates

Commands used the existing offline dependency environment and isolated workspace caches.

- `ruff check src tests`: `All checks passed!`
- `mypy src`: `Success: no issues found in 181 source files`

The initial sandbox attempts could not access the user uv cache. The exact offline commands were rerun outside the filesystem sandbox against the already installed cache; no dependency was downloaded and no provider was contacted.

## Founder frontend gates

From `frontend/founder`:

- `npm test`: `50/50` tests passed
- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run build`: passed; `5/5` static pages built and the direction contract verified

The sandbox build first hit Windows `spawn EPERM`; the same build passed outside the sandbox. No frontend package drift remained after the gates.

## Capability truth at this revision

| Capability | Status | Evidence boundary |
| --- | --- | --- |
| Safe upload and archive inspection | available | hostile archive suite is part of Gate C |
| PDF and DOCX parsing | available | active `StartupParsingService` path and parser suite |
| PNG/JPEG OCR | available | active `StartupParsingService` path and offline parser suite |
| CSV/XLSX parsing | partial | component suite GREEN; not wired into active startup parser |
| ZIP | partial | securely expanded during ingest; members then follow their own format paths |
| Primary startup workflow | available at current bounded contract | API, graph, report, provider/budget focused suites GREEN |
| Universal `StartupProfile` | planned Queue 1 | no canonical persisted profile yet |
| Deep startup market analysis | planned | product capability contract still marks it planned |

## Environmental warnings and ownership

- WeasyPrint native libraries are unavailable on this machine. Gate B still passed using the designed ReportLab fallback and produced approved report artifacts.
- LangGraph emitted a forward-compatibility warning for checkpoint deserialization of `AnalysisPlan`. This is non-blocking for Queue 0 but should be explicitly allowlisted or made strict before production hardening.
- Pre-existing modified files `artifacts/ui/founder-desktop.png` and `artifacts/ui/founder-mobile.png` belong to earlier UI work and were not modified or reverted by Queue 0.
- Generated Gate C output and temporary test directories remain uncommitted runtime evidence. The canonical hashes above are the integrity references.

## Review

The final independent Gate C review returned PASS with zero blocking findings. The only low-priority note—legacy `LANGCHAIN_TRACING` not being disabled by direct Python invocation—was fixed before the final artifact was generated.

## Queue transition

Queue 1 may start. Its first integration slice must preserve this baseline and close the filename/MIME metadata loss plus CSV/XLSX active-parser gap before claiming universal upload.
