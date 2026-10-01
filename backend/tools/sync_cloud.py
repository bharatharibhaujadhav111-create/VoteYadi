"""Accuracy-first R2 PDF processor for local use and GitHub Actions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.text_utils import devanagari_to_roman, normalize  # noqa: E402


class QualityError(RuntimeError):
    def __init__(self, message: str, report: dict) -> None:
        super().__init__(message)
        self.report = report


def load_env(path: Path) -> None:
    """Load local secrets when present; GitHub supplies environment variables."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


class Supabase:
    def __init__(self, url: str, key: str) -> None:
        self.base = url.rstrip("/") + "/rest/v1"
        headers = {"apikey": key, "content-type": "application/json"}
        if not key.startswith("sb_secret_"):
            headers["authorization"] = f"Bearer {key}"
        self.client = httpx.Client(timeout=180, headers=headers)

    def request(self, method: str, path: str, *, data=None, prefer="return=representation"):
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.request(
                    method, f"{self.base}/{path}", json=data, headers={"prefer": prefer}
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RuntimeError(f"Supabase temporary error {response.status_code}: {response.text}")
                if response.is_error:
                    raise RuntimeError(f"Supabase {response.status_code}: {response.text}")
                return response.json() if response.content else None
            except (httpx.TransportError, RuntimeError) as exc:
                last_error = exc
                permanent = isinstance(exc, RuntimeError) and "temporary" not in str(exc)
                if attempt == 2 or permanent:
                    raise
                time.sleep(2 ** attempt)
        raise last_error or RuntimeError("Supabase request failed")

    def rpc(self, name: str, data: dict):
        return self.request("POST", f"rpc/{name}", data=data)


def safe_temp_name(name: str) -> str:
    clean = re.sub(r"[^\w .-]", "_", name, flags=re.UNICODE).strip() or "document.pdf"
    return clean if clean.lower().endswith(".pdf") else clean + ".pdf"


def voter_rows(document: dict, result) -> list[dict]:
    if not document.get("village_id"):
        raise RuntimeError("Assign this PDF to a village before indexing")
    rows = []
    for i, record in enumerate(result.records):
        raw = record.to_row()
        age_text = str(raw.get("age") or "").strip()
        name = str(raw.get("name") or "").strip()
        relation_name = str(raw.get("relation_name") or "").strip()
        rows.append({
            "record_index": i,
            "name": name,
            "name_normalized": normalize(name),
            "name_latin": normalize(devanagari_to_roman(name)),
            "relation_name": relation_name,
            "relation_name_normalized": normalize(relation_name),
            "relation_name_latin": normalize(devanagari_to_roman(relation_name)),
            "relation_type": raw.get("relation_type") or "",
            "epic": str(raw.get("epic") or "").strip(),
            "serial": str(raw.get("serial") or "").strip(),
            "house": str(raw.get("house") or "").strip(),
            "age": int(age_text) if age_text.isdigit() and int(age_text) <= 130 else None,
            "gender": raw.get("gender") or "",
            "part": str(raw.get("part") or "").strip(),
            "section": str(raw.get("section") or "").strip(),
            "page": int(raw.get("page") or 1),
            "script": "devanagari" if re.search(r"[\u0900-\u097f]", name) else "latin",
        })
    return rows


def validate(rows: list[dict], pages: int, ocr_pages: int) -> dict:
    """Hold suspicious OCR for review instead of publishing it."""
    names = [r["name"] for r in rows]
    serials = [r["serial"] for r in rows if r["serial"]]
    blank_serials = len(rows) - len(serials)
    invalid_serials = sum(not str(value).isdigit() for value in serials)
    duplicate_serials = len(serials) - len(set(serials))
    numeric_serials = {int(value) for value in serials if str(value).isdigit()}
    sequence_gaps = (set(range(min(numeric_serials), max(numeric_serials) + 1)) - numeric_serials
                     if numeric_serials else set())
    page_ranges = []
    for page in sorted({int(r["page"]) for r in rows}):
        values = [int(r["serial"]) for r in rows
                  if int(r["page"]) == page and str(r["serial"]).isdigit()]
        if values:
            page_ranges.append((page, min(values), max(values)))
    serial_order_anomalies = [
        {"previous_page": previous[0], "page": current[0],
         "previous_max": previous[2], "current_min": current[1]}
        for previous, current in zip(page_ranges, page_ranges[1:])
        if previous[2] >= current[1]
    ]
    epics = [r["epic"].replace(" ", "").upper() for r in rows if r["epic"]]
    dev_names = sum(bool(re.search(r"[\u0900-\u097f]", name)) for name in names)
    invalid_pages = sum(not 1 <= int(r["page"]) <= pages for r in rows)
    duplicate_epics = len(epics) - len(set(epics))
    normalized_names = [r["name_normalized"] for r in rows if r["name_normalized"]]
    duplicate_names = len(normalized_names) - len(set(normalized_names))
    duplicate_records = len(rows) - len({
        (r["name_normalized"], r["relation_name_normalized"], r["serial"], r["page"])
        for r in rows
    })
    mixed_script = [
        {"serial": r["serial"], "page": r["page"]}
        for r in rows
        if re.search(r"[A-Za-z]", r["name"] + " " + r["relation_name"])
    ]
    report = {
        "version": 2,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "ocr_pages": ocr_pages,
        "records": len(rows),
        "records_per_page": round(len(rows) / max(pages, 1), 2),
        "marathi_name_ratio": round(dev_names / max(len(names), 1), 4),
        "serial_coverage": round(len(serials) / max(len(rows), 1), 4),
        "blank_serials": blank_serials,
        "invalid_serials": invalid_serials,
        "duplicate_serials": duplicate_serials,
        "serial_sequence_missing": len(sequence_gaps),
        "serial_sequence_unexpected": 0,
        "serial_order_anomalies": serial_order_anomalies,
        "duplicate_epics": duplicate_epics,
        "duplicate_names": duplicate_names,
        "duplicate_records": duplicate_records,
        "invalid_page_records": invalid_pages,
        "mixed_script_records": len(mixed_script),
        "mixed_script_examples": mixed_script[:10],
        "checks": [],
        "warnings": [],
    }
    failures = []
    if pages <= 0:
        failures.append("PDF has no readable pages")
    if len(rows) < max(10, pages * 3):
        failures.append(f"Only {len(rows)} voter records were extracted from {pages} pages")
    if report["marathi_name_ratio"] < 0.60:
        failures.append("Too few extracted names contain Marathi text")
    if blank_serials:
        failures.append(f"{blank_serials} voter serial numbers are blank")
    if invalid_serials:
        failures.append(f"{invalid_serials} voter serial numbers are not numeric")
    if duplicate_serials:
        failures.append(f"{duplicate_serials} voter serial numbers are duplicated")
    if sequence_gaps:
        failures.append(f"Voter serial sequence has {len(sequence_gaps)} unresolved gaps")
    if serial_order_anomalies:
        failures.append(f"Voter serial ranges overlap or go backwards across {len(serial_order_anomalies)} page boundaries")
    if invalid_pages:
        failures.append(f"{invalid_pages} records refer to invalid PDF pages")
    if duplicate_names:
        report["warnings"].append(f"{duplicate_names} repeated voter names; retained as separate PDF records")
    if duplicate_epics:
        report["warnings"].append(f"{duplicate_epics} repeated EPIC numbers; retained with each record's page and serial")
    if duplicate_records:
        report["warnings"].append(f"{duplicate_records} identical parsed voter blocks; retained for review")
    if mixed_script:
        failures.append(f"{len(mixed_script)} Marathi voter names contain English OCR fragments")
    report["checks"] = failures or ["passed"]
    report["status"] = "review" if failures else "passed"
    if failures:
        raise QualityError("; ".join(failures), report)
    return report


def worker_name() -> str:
    run = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    job = os.environ.get("GITHUB_JOB", "sync")
    return f"github:{run}:{attempt}:{job}" if run != "local" else f"local:{os.getpid()}"


def pending_documents(supabase: Supabase, limit: int) -> list[dict]:
    fields = "id,original_filename,status,uploaded_at,processing_started_at,village_id,villages(name)"
    path = (
        f"documents?select={fields}&village_id=not.is.null&status=in.(uploaded,queued,processing)"
        f"&order=uploaded_at.asc&limit=100"
    )
    cutoff = datetime.now(timezone.utc).timestamp() - 6 * 60 * 60
    pending = []
    for item in supabase.request("GET", path) or []:
        if item["status"] in ("uploaded", "queued"):
            pending.append(item)
        elif item.get("processing_started_at"):
            started = datetime.fromisoformat(item["processing_started_at"].replace("Z", "+00:00"))
            if started.timestamp() < cutoff:
                pending.append(item)
    return pending[:max(1, min(limit, 100))]


def process_document(
    supabase: Supabase, document_id: str, workers: int, claim: bool, final_attempt: bool
) -> int:
    import boto3  # Imported only by processor jobs, not the lightweight queue discovery.
    from app.pdf_manager.pdf_parser import parse_pdf

    worker = worker_name()
    if claim:
        claimed = supabase.rpc("claim_document_for_indexing", {
            "document_uuid": document_id, "worker_name": worker,
        })
        if claimed is not True:
            print(json.dumps({"document": document_id, "status": "skipped", "reason": "not claimable; inspect its current status"}))
            return 3

    query = (
        "documents?select=id,village_id,original_filename,r2_key,status,size_bytes,r2_etag"
        f"&id=eq.{document_id}&limit=1"
    )
    documents = supabase.request("GET", query) or []
    if not documents:
        raise RuntimeError("Document not found")
    document = documents[0]
    if document.get("status") != "processing":
        raise RuntimeError(f"Document is not claimed (status={document.get('status')})")

    r2 = boto3.client(
        "s3", endpoint_url=required("R2_ENDPOINT_URL"),
        aws_access_key_id=required("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=required("R2_SECRET_ACCESS_KEY"), region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET", "voteyadi-pdfs")
    report: dict = {}
    try:
        with tempfile.TemporaryDirectory(prefix="voteyadi-") as folder:
            local = Path(folder) / safe_temp_name(document["original_filename"])
            r2.download_file(bucket, document["r2_key"], str(local))
            if local.stat().st_size < 1024 or local.read_bytes()[:5] != b"%PDF-":
                raise QualityError("Downloaded object is not a valid PDF", {"status": "review"})
            expected_size = int(document.get("size_bytes") or 0)
            if expected_size and local.stat().st_size != expected_size:
                raise RuntimeError("Downloaded PDF size does not match the uploaded file")
            result = parse_pdf(
                local, workers=max(1, min(workers, 2)),
                progress=lambda done, total: print(f"pages {done}/{total}", flush=True),
            )
        rows = voter_rows(document, result)
        report = validate(rows, result.pages, result.ocr_pages)
        inserted = supabase.rpc("publish_document_index", {
            "document_uuid": document_id, "worker_name": worker, "voter_rows": rows,
            "parsed_pages": result.pages, "parsed_ocr_pages": result.ocr_pages,
            "report": report,
        })
        print(json.dumps({
            "document": document_id, "status": "ready", "records": inserted,
            "pages": result.pages, "ocr_pages": result.ocr_pages, "quality": report,
        }, ensure_ascii=False))
        return 0
    except QualityError as exc:
        supabase.rpc("reject_document_index", {
            "document_uuid": document_id, "worker_name": worker,
            "new_status": "needs_review", "failure_message": str(exc), "report": exc.report,
        })
        print(json.dumps({"document": document_id, "status": "needs_review", "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        try:
            supabase.rpc("reject_document_index", {
                "document_uuid": document_id, "worker_name": worker,
                "new_status": "failed" if final_attempt else "queued",
                "failure_message": str(exc), "report": report,
            })
        except Exception as status_error:
            print(f"Could not update failure status: {status_error}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and atomically publish one R2 voter PDF")
    parser.add_argument("--list-pending", action="store_true", help="Print JSON for a GitHub matrix")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--document", help="Process exactly one document UUID")
    parser.add_argument("--claim", action="store_true", help="Atomically claim before work")
    parser.add_argument("--final-attempt", action="store_true", help="Mark infrastructure failure final")
    parser.add_argument("--workers", type=int, default=2, help="OCR processes inside this PDF job (max 2)")
    args = parser.parse_args()
    load_env(ROOT / ".env.local")
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip() or required("SUPABASE_SERVICE_ROLE_KEY")
    supabase = Supabase(required("SUPABASE_URL"), key)
    if args.list_pending:
        items = pending_documents(supabase, args.limit)
        print(json.dumps([{"document_id": item["id"], "name": item["original_filename"]} for item in items]))
        return 0
    if not args.document:
        parser.error("--document is required unless --list-pending is used")
    return process_document(supabase, args.document, args.workers, args.claim, args.final_attempt)


if __name__ == "__main__":
    raise SystemExit(main())
