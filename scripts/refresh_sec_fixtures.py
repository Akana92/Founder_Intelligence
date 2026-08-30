from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any

import httpx

from due_diligence_agent.adapters.http.snapshot_cache import verify_fixture_manifest


SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
LICENSE_CLASS = "public_primary"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--cik", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    user_agent = os.environ.get("DDA_SEC_USER_AGENT", "").strip()
    if not user_agent:
        parser.exit(2, "DDA_SEC_USER_AGENT is required before refreshing SEC fixtures\n")

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        _refresh_into(
            temp_root,
            ticker=args.ticker,
            cik=_normalize_cik(args.cik),
            as_of=date.fromisoformat(args.as_of),
            user_agent=user_agent,
        )
        verify_fixture_manifest(temp_root / "manifest.json")
        _publish_directory(temp_root, output)
    except Exception:
        if temp_root.exists():
            shutil.rmtree(temp_root)
        raise
    return 0


def _refresh_into(
    output: Path,
    *,
    ticker: str,
    cik: str,
    as_of: date,
    user_agent: str,
) -> None:
    limiter = _SyncLimiter()
    ticker_slug = _ticker_slug(ticker)
    with httpx.Client(headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}) as client:
        submissions_url = f"{SEC_DATA_BASE}/submissions/CIK{cik}.json"
        companyfacts_url = f"{SEC_DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        submissions = _get_json(client, limiter, submissions_url)
        companyfacts = _get_json(client, limiter, companyfacts_url)
        _write_json(output / "submissions.json", submissions)
        _write_json(output / "companyfacts.json", companyfacts)

        filing_entries = _select_required_filings(submissions)
        fetched_files: dict[str, dict[str, Any]] = {
            "submissions.json": _manifest_entry(submissions_url, output / "submissions.json"),
            "companyfacts.json": _manifest_entry(companyfacts_url, output / "companyfacts.json"),
        }
        for form, entry in filing_entries.items():
            archive_url = _archive_url(cik, entry["accession"], entry["primary_document"])
            file_name = f"{ticker_slug}-2026-10k.html" if form == "10-K" else f"{ticker_slug}-2026-10q.html"
            _write_bytes(output / file_name, _get_bytes(client, limiter, archive_url))
            fetched_files[file_name] = _manifest_entry(
                archive_url,
                output / file_name,
                accession_number=entry["accession"],
                filing_acceptance_at=entry["filing_acceptance_at"],
                filing_date=entry["filing_date"],
                report_period_end=entry["report_period_end"],
                effective_at=entry["effective_at"],
            )

        xbrl_entry = filing_entries["10-K"]
        xbrl_name = f"{ticker_slug}-2026-xbrl.xml"
        index_url = _archive_url(cik, xbrl_entry["accession"], "index.json")
        xbrl_document = _select_xbrl_instance(_get_json(client, limiter, index_url))
        xbrl_url = _archive_url(cik, xbrl_entry["accession"], xbrl_document)
        _write_bytes(output / xbrl_name, _get_bytes(client, limiter, xbrl_url))
        fetched_files[xbrl_name] = _manifest_entry(
            xbrl_url,
            output / xbrl_name,
            accession_number=xbrl_entry["accession"],
            filing_acceptance_at=xbrl_entry["filing_acceptance_at"],
            filing_date=xbrl_entry["filing_date"],
            report_period_end=xbrl_entry["report_period_end"],
            effective_at=xbrl_entry["effective_at"],
        )
    _write_json(
        output / "manifest.json",
        {
            "provider": "sec",
            "ticker": ticker,
            "cik": cik,
            "as_of": as_of.isoformat(),
            "license_class": LICENSE_CLASS,
            "fixture_provenance": "refreshed from SEC public endpoints with declared User-Agent",
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "files": fetched_files,
        },
    )


def _get_json(client: httpx.Client, limiter: _SyncLimiter, url: str) -> dict[str, Any]:
    return json.loads(_get_bytes(client, limiter, url).decode("utf-8"))


def _get_bytes(client: httpx.Client, limiter: _SyncLimiter, url: str) -> bytes:
    for attempt in range(1, 6):
        limiter.acquire()
        response = client.get(url)
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            if attempt == 5:
                response.raise_for_status()
            time.sleep(_sync_retry_after_seconds(response, _refresh_now()))
            continue
        response.raise_for_status()
        return response.content
    raise RuntimeError("unreachable refresh retry loop")


def _select_required_filings(submissions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    recent = submissions["filings"]["recent"]
    selected: dict[str, dict[str, Any]] = {}
    for index, form in enumerate(recent["form"]):
        if form not in {"10-K", "10-Q"} or form in selected:
            continue
        selected[form] = {
            "accession": recent["accessionNumber"][index],
            "primary_document": recent["primaryDocument"][index],
            "filing_acceptance_at": recent["acceptanceDateTime"][index],
            "filing_date": recent["filingDate"][index],
            "report_period_end": recent["reportDate"][index],
            "effective_at": _optional_recent_value(recent, "effectivenessDate", index),
        }
    missing = {"10-K", "10-Q"} - set(selected)
    if missing:
        raise ValueError(f"missing required filing forms:{','.join(sorted(missing))}")
    return selected


def _archive_url(cik: str, accession: str, document: str) -> str:
    return (
        f"{SEC_ARCHIVE_BASE}/{int(cik)}/"
        f"{accession.replace('-', '')}/{document}"
    )


def _select_xbrl_instance(index_json: dict[str, Any]) -> str:
    items = index_json.get("directory", {}).get("item", [])
    if not isinstance(items, list):
        raise ValueError("invalid filing index")
    xml_candidates: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).upper()
        name = str(item.get("name", ""))
        if description == "EXTRACTED XBRL INSTANCE DOCUMENT" and name.lower().endswith(".xml"):
            return name
        if _is_viable_xbrl_instance_name(name):
            xml_candidates.append(name)
    preferred = [name for name in xml_candidates if name.lower().endswith("_htm.xml")]
    candidates = preferred or xml_candidates
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("xbrl instance not found")
    raise ValueError("ambiguous xbrl instance")


def _is_viable_xbrl_instance_name(name: str) -> bool:
    lower = name.lower()
    if not lower.endswith(".xml"):
        return False
    if lower == "filingsummary.xml" or lower.endswith(".xsd"):
        return False
    excluded_suffixes = ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")
    return not lower.endswith(excluded_suffixes)


def _manifest_entry(
    retrieval_url: str,
    path: Path,
    *,
    accession_number: str | None = None,
    filing_acceptance_at: str | None = None,
    filing_date: str | None = None,
    report_period_end: str | None = None,
    effective_at: str | None = None,
) -> dict[str, Any]:
    entry = {
        "retrieval_url": retrieval_url,
        "license_class": LICENSE_CLASS,
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }
    if accession_number is not None:
        entry["accession_number"] = accession_number
    if filing_acceptance_at is not None:
        entry["filing_acceptance_at"] = filing_acceptance_at
    if filing_date is not None:
        entry["filing_date"] = filing_date
    if report_period_end is not None:
        entry["report_period_end"] = report_period_end
    if accession_number is not None:
        entry["effective_at"] = effective_at
    return entry


def _optional_recent_value(recent: dict[str, Any], key: str, index: int) -> str | None:
    values = recent.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _publish_directory(temp_root: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.backup.{os.getpid()}")
    if backup.exists():
        shutil.rmtree(backup)
    backup_created = False
    if output.exists():
        output.rename(backup)
        backup_created = True
    try:
        temp_root.rename(output)
    except Exception:
        if backup_created and backup.exists() and not output.exists():
            backup.rename(output)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def _sync_retry_after_seconds(response: httpx.Response, now: datetime) -> float:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return 1.0
    if value.isdigit():
        return min(30.0, float(value))
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return 1.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return min(30.0, max(0.0, (parsed.astimezone(UTC) - now).total_seconds()))


def _refresh_now() -> datetime:
    return datetime.now(UTC)


def _normalize_cik(cik: str) -> str:
    digits = "".join(character for character in cik if character.isdigit())
    if not digits:
        raise ValueError("cik must contain digits")
    return digits.zfill(10)


def _ticker_slug(ticker: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", ticker.strip().lower()).strip("-")
    if not slug:
        raise ValueError("ticker is required")
    return slug


class _SyncLimiter:
    def __init__(self) -> None:
        self._timestamps: list[float] = []

    def acquire(self) -> None:
        now = time.monotonic()
        self._timestamps = [timestamp for timestamp in self._timestamps if now - timestamp < 1.0]
        if len(self._timestamps) >= 10:
            wait_for = 1.0 - (now - self._timestamps[0])
            time.sleep(max(0.0, wait_for))
            now = time.monotonic()
            self._timestamps = [timestamp for timestamp in self._timestamps if now - timestamp < 1.0]
        self._timestamps.append(now)


if __name__ == "__main__":
    raise SystemExit(main())
