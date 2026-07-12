"""
Scraping endpoints (Abschnitt 1).

- Exposes the grouped file-type catalogue (Dokument / Bild / Media).
- Lists the AI models the current user may choose (based on their roles).
- Starts a scrape as a background job (``POST /api/scrape`` returns a
  ``job_id`` immediately) and exposes its live progress + final results via
  ``GET /api/scrape/status/{job_id}``.
- Records each run in a local ``Log.txt`` and serves the last run's log section.

Execution backend
-----------------
Each run executes in a background thread so the HTTP request stays short —
otherwise slow (image/media-heavy) runs would die on a browser / proxy
timeout, which is what made non-PDF / multi-type scrapes look like they hung.

The thread dispatches the work to one of two backends:

- **AWS Lambda** when ``LAMBDA_FUNCTION_NAME`` is set (production). The call
  uses boto3; set the region via ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` and let
  credentials come from the standard AWS chain (instance role in EC2).
- **Local subprocess** (``python run.py …``) otherwise, so a full repo checkout
  can scrape without a deployed Lambda (dev / demo).

Notes
-----
The AI model selection is a *gating requirement* only (no real ML processing
yet). The job registry is in-memory (cleared on restart); the durable record of
every run lives in ``Log.txt``.
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..auth import get_current_user
from ..db import get_connection
from webscraper.utils.url_sources import (
    extract_urls_from_csv_text,
    extract_urls_from_html_text,
    extract_urls_from_text_lines,
)

# Decisions considered "relevant" to surface to the user (spec §9): confident
# positives plus the uncertain review band. Confident negatives are hidden.
_RELEVANT_DECISIONS = ("automatic_positive", "needs_review")

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

# Project root (scrape.py -> routers -> webapp -> project root) holds Log.txt.
# Overridable via LOG_FILE so it can live on a persistent volume in Docker.
LOG_FILE = Path(
    os.getenv("LOG_FILE", str(Path(__file__).resolve().parent.parent.parent / "Log.txt"))
)

RUN_MARKER = "===== SCRAPE RUN"

# Marker that run.py prints in front of its JSON summary line (must match
# run.py's SUMMARY_MARKER). Used by the local-subprocess fallback.
_SUMMARY_MARKER = "__SCRAPE_SUMMARY__"

# ---------------------------------------------------------------------------
# In-memory job registry
#
# A scrape can take from a few seconds (one PDF) to a couple of minutes
# (image/media-heavy pages). Running it synchronously inside the POST request
# holds the HTTP connection open the whole time, so slow runs die on a browser
# / reverse-proxy timeout — which looked like the scraper "hanging" whenever a
# non-PDF or multi-type run was started.
#
# Instead we run each scrape in a background thread and let the frontend poll
# GET /api/scrape/status/{job_id}. The registry is in-memory (lost on restart);
# the durable record of every run still lives in Log.txt.
# ---------------------------------------------------------------------------
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_LOG_LOCK = threading.Lock()
_MAX_JOBS_KEPT = 50

# Grouped catalogue of supported file types. Captions are shown in the UI.
FILE_TYPE_GROUPS: dict[str, list[dict]] = {
    "Dokument": [
        {"ext": "pdf", "label": "PDF"},
        {"ext": "doc", "label": "Word (.doc)"},
        {"ext": "docx", "label": "Word (.docx)"},
        {"ext": "xls", "label": "Excel (.xls)"},
        {"ext": "xlsx", "label": "Excel (.xlsx)"},
        {"ext": "ppt", "label": "PowerPoint (.ppt)"},
        {"ext": "pptx", "label": "PowerPoint (.pptx)"},
        {"ext": "odt", "label": "OpenDocument Text"},
        {"ext": "ods", "label": "OpenDocument Sheet"},
        {"ext": "odp", "label": "OpenDocument Präsentation"},
        {"ext": "rtf", "label": "Rich Text (.rtf)"},
        {"ext": "txt", "label": "Text (.txt)"},
        {"ext": "csv", "label": "CSV"},
    ],
    "Bild": [
        {"ext": "jpg", "label": "JPEG (.jpg)"},
        {"ext": "jpeg", "label": "JPEG (.jpeg)"},
        {"ext": "png", "label": "PNG"},
        {"ext": "gif", "label": "GIF"},
        {"ext": "bmp", "label": "BMP"},
        {"ext": "tiff", "label": "TIFF"},
        {"ext": "svg", "label": "SVG"},
        {"ext": "webp", "label": "WebP"},
    ],
    "Media": [
        {"ext": "mp3", "label": "MP3"},
        {"ext": "wav", "label": "WAV"},
        {"ext": "flac", "label": "FLAC"},
        {"ext": "aac", "label": "AAC"},
        {"ext": "ogg", "label": "OGG"},
        {"ext": "mp4", "label": "MP4"},
        {"ext": "avi", "label": "AVI"},
        {"ext": "mov", "label": "MOV"},
        {"ext": "mkv", "label": "MKV"},
        {"ext": "webm", "label": "WebM"},
        {"ext": "wmv", "label": "WMV"},
    ],
}

_ALLOWED_EXTS = {
    item["ext"] for group in FILE_TYPE_GROUPS.values() for item in group
}


@router.get("/filetypes")
def get_file_types(user: dict = Depends(get_current_user)):
    """Grouped catalogue of selectable file types."""
    return {"groups": FILE_TYPE_GROUPS}


@router.get("/models")
def get_available_models(user: dict = Depends(get_current_user)):
    """AI models the current user may use, based on their assigned roles."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT m.id, m.bezeichnung FROM SYS_AI_MODEL m "
            "JOIN SYS_MODEL_ROLES mr ON mr.model_id = m.id "
            "JOIN SYS_USER_ROLES ur ON ur.role_id = mr.role_id "
            "WHERE ur.user_id = ? ORDER BY m.bezeichnung",
            (user["id"],),
        ).fetchall()
        return {"models": [dict(r) for r in rows]}
    finally:
        conn.close()


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _append_log(lines: list[str]) -> None:
    # Serialised because scrape runs execute on background threads that may
    # finish while another run is starting.
    with _LOG_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")


def _parse_summary(raw_payload: str) -> dict | None:
    """Dig the run summary out of the Lambda response payload.

    Shape: ``{"statusCode": ..., "body": "{...\"summary\": {...}}"}``.
    """
    try:
        outer = json.loads(raw_payload)
        body = outer.get("body")
        inner = json.loads(body) if isinstance(body, str) else (body or {})
        summary = inner.get("summary")
        return summary if isinstance(summary, dict) else None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _invoke_lambda(payload: dict) -> tuple[bool, str, dict | None]:
    """Invoke the deployed Lambda synchronously. Returns (ok, detail, summary)."""
    function_name = os.getenv("LAMBDA_FUNCTION_NAME")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
    if not function_name:
        return False, "LAMBDA_FUNCTION_NAME ist nicht konfiguriert.", None

    try:
        import boto3
        from botocore.config import Config

        cfg = Config(
            read_timeout=900, connect_timeout=10, retries={"max_attempts": 0}
        )
        client = boto3.client("lambda", region_name=region, config=cfg)
        resp = client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        body = resp["Payload"].read().decode("utf-8")
        status = resp.get("StatusCode")
        if resp.get("FunctionError"):
            return False, f"Lambda-Fehler ({status}): {body}", None
        return True, f"Lambda-Antwort ({status}): {body}", _parse_summary(body)
    except Exception as exc:  # noqa: BLE001 — surface any AWS/boto error to the log
        return False, f"Aufruf fehlgeschlagen: {exc}", None


def _extract_marker_summary(stdout: str | None) -> dict | None:
    """Pull the JSON summary printed by run.py (``__SCRAPE_SUMMARY__ {...}``)."""
    if not stdout:
        return None
    for line in stdout.splitlines():
        idx = line.find(_SUMMARY_MARKER)
        if idx != -1:
            payload = line[idx + len(_SUMMARY_MARKER):].strip()
            try:
                return json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                return None
    return None


def _run_local(payload: dict) -> tuple[bool, str, dict | None]:
    """Run the scraper locally via ``run.py`` (fallback when no Lambda is set).

    Lets the web app work on a full repo checkout without a deployed Lambda —
    the same code path Lambda uses, just invoked in-process. Returns
    ``(ok, detail, summary)``.
    """
    project_dir = Path(__file__).resolve().parent.parent.parent
    run_py = project_dir / "run.py"
    if not run_py.exists():
        return (
            False,
            "Kein LAMBDA_FUNCTION_NAME gesetzt und run.py lokal nicht gefunden.",
            None,
        )

    cmd = [sys.executable, "run.py", *payload["urls"], "--max-jobs", "10"]
    if payload.get("job_id"):
        cmd += ["--batch-id", payload["job_id"]]
    file_types = payload.get("file_types")
    if file_types:
        cmd += ["--file-types", ",".join(file_types)]
    # The pre-crawl HEAD probe (requests) can false-negative behind SSL-
    # intercepting proxies or on servers that block HEAD. Set SCRAPE_PING=false
    # to skip it and let Scrapy validate during the crawl instead.
    if os.getenv("SCRAPE_PING", "true").lower() != "true":
        cmd.append("--no-ping")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=900,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return False, "Lokaler Scrape-Timeout nach 900s.", None
    except Exception as exc:  # noqa: BLE001 — surface any launch error to the log
        return False, f"Lokaler Lauf fehlgeschlagen: {exc}", None

    summary = _extract_marker_summary(result.stdout)
    ok = result.returncode == 0
    detail = f"Lokaler Lauf beendet (exit={result.returncode})."
    if not ok and result.stderr:
        detail += " " + result.stderr.strip().splitlines()[-1][:300]
    return ok, detail, summary


def _run_scrape(payload: dict) -> tuple[bool, str, dict | None]:
    """Dispatch a scrape to Lambda when configured, else run it locally."""
    if os.getenv("LAMBDA_FUNCTION_NAME"):
        return _invoke_lambda(payload)
    return _run_local(payload)


def _prune_jobs() -> None:
    """Keep the in-memory registry bounded (call while holding _JOBS_LOCK)."""
    if len(_JOBS) <= _MAX_JOBS_KEPT:
        return
    # Drop the oldest finished jobs first.
    finished = sorted(
        (jid for jid, j in _JOBS.items() if j.get("finished_at")),
        key=lambda jid: _JOBS[jid]["finished_at"],
    )
    for jid in finished[: len(_JOBS) - _MAX_JOBS_KEPT]:
        _JOBS.pop(jid, None)


def _execute_scrape(
    job_id: str,
    urls: list[str],
    selected: list[str],
    model_label: str,
    username: str,
    position: str,
) -> None:
    """Background worker: run the scrape and record its outcome + log lines."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload = {"urls": urls, "file_types": selected, "job_id": job_id}

    _append_log(
        [
            f"{RUN_MARKER} {now} | job={job_id} =====",
            f"Benutzer: {username} ({position})",
            f"KI-Modell: {model_label}",
            f"Dateiformate: {', '.join(selected)}",
            f"URLs ({len(urls)}): {', '.join(urls)}",
            "Starte Scrape…",
        ]
    )

    ok, detail, summary = _run_scrape(payload)

    log_lines = [detail]
    if summary:
        log_lines.append(
            "Ergebnis: {found} gefunden, {dl} heruntergeladen, "
            "{mb:.2f} MB, {dur:.1f}s".format(
                found=summary.get("files_found", 0),
                dl=summary.get("files_downloaded", 0),
                mb=summary.get("bytes_downloaded", 0) / (1024 * 1024),
                dur=summary.get("duration_seconds", 0),
            )
        )
    log_lines.append("Lauf beendet." if ok else "Lauf mit Fehler beendet.")
    _append_log(log_lines)

    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(
                status="done" if ok else "error",
                ok=ok,
                detail=detail,
                summary=summary,
                finished_at=time.time(),
            )


@router.post("")
def start_scrape(
    file_types: str = Form(""),
    model_id: int | None = Form(None),
    url: str = Form(""),
    file: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
):
    """Validate inputs, collect URLs, invoke Lambda and log the run."""
    # --- file types -------------------------------------------------------
    selected = [ft.strip().lower() for ft in file_types.split(",") if ft.strip()]
    invalid = [ft for ft in selected if ft not in _ALLOWED_EXTS]
    if not selected:
        raise HTTPException(status_code=400, detail="Mindestens ein Dateiformat wählen.")
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unbekannte Dateiformate: {', '.join(invalid)}."
        )

    # --- AI model -------------------------------------------------------
    # TEMPORARY: the model is optional until a real model has been trained. When
    # one *is* selected it must still be one the user is allowed to use.
    model_label = "(kein Modell – Testlauf)"
    if model_id is not None:
        conn = get_connection()
        try:
            allowed = conn.execute(
                "SELECT 1 FROM SYS_MODEL_ROLES mr "
                "JOIN SYS_USER_ROLES ur ON ur.role_id = mr.role_id "
                "WHERE mr.model_id = ? AND ur.user_id = ? LIMIT 1",
                (model_id, user["id"]),
            ).fetchone()
            model_row = conn.execute(
                "SELECT bezeichnung FROM SYS_AI_MODEL WHERE id = ?", (model_id,)
            ).fetchone()
        finally:
            conn.close()
        if model_row is None or allowed is None:
            raise HTTPException(
                status_code=400, detail="Ungültiges oder nicht erlaubtes KI-Modell."
            )
        model_label = model_row["bezeichnung"]

    # --- collect URLs (direct + uploaded CSV/HTML) ------------------------
    urls: list[str] = []
    if url.strip():
        urls.append(url.strip())

    if file is not None and file.filename:
        raw = file.file.read().decode("utf-8-sig", errors="replace")
        name = file.filename.lower()
        if name.endswith(".csv"):
            urls += extract_urls_from_csv_text(raw)
        elif name.endswith((".html", ".htm")):
            urls += extract_urls_from_html_text(raw)
        elif name.endswith(".txt"):
            urls += extract_urls_from_text_lines(raw)
        else:
            raise HTTPException(
                status_code=400,
                detail="Nur .csv, .html oder .txt Dateien werden unterstützt.",
            )

    urls = _dedupe(urls)
    if not urls:
        raise HTTPException(
            status_code=400,
            detail="Keine URL angegeben bzw. keine URLs in der Datei gefunden.",
        )

    # --- start the run in the background ---------------------------------
    # Return immediately with a job_id; the frontend polls /status/{job_id}.
    # This keeps the request short so slow (image/media) runs no longer die on
    # a browser / proxy timeout.
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "ok": None,
            "detail": "",
            "summary": None,
            "urls": urls,
            "file_types": selected,
            "model_label": model_label,
        }
        _prune_jobs()

    thread = threading.Thread(
        target=_execute_scrape,
        args=(job_id, urls, selected, model_label, user["username"], user["position"]),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "running",
        "urls": urls,
        "file_types": selected,
    }


def _job_view(job: dict) -> dict:
    """Serialise a registry entry for the status endpoint."""
    end = job["finished_at"] if job["finished_at"] is not None else time.time()
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "ok": job["ok"],
        "detail": job["detail"],
        "summary": job["summary"],
        "urls": job["urls"],
        "file_types": job["file_types"],
        "model_label": job["model_label"],
        "elapsed_seconds": round(max(0.0, end - job["started_at"]), 1),
    }


@router.get("/status/{job_id}")
def get_status(job_id: str, user: dict = Depends(get_current_user)):
    """Poll the state of a scrape run started via ``POST /api/scrape``."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        view = _job_view(job) if job is not None else None
    if view is None:
        raise HTTPException(status_code=404, detail="Unbekannte oder abgelaufene Job-ID.")
    return view


# ---------------------------------------------------------------------------
# Classification results (the "relevant Modulhandbücher" view)
#
# During a scrape the ClassificationPipeline writes a per-run review manifest
# (JSONL). Locally it lands under output/_review/; in production the Lambda run
# uploads it to s3://<bucket>/manifests/<job_id>.jsonl. These endpoints read it
# back, surface the relevant documents, and serve downloads.
# ---------------------------------------------------------------------------

def _manifest_dir() -> Path:
    env = os.getenv("REVIEW_MANIFEST_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "output" / "_review"


def _load_manifest(job_id: str) -> list[dict] | None:
    """Load a run's manifest from local disk, or S3 if configured. None if absent."""
    local = _manifest_dir() / f"manifest_{job_id}.jsonl"
    text: str | None = None
    if local.exists():
        text = local.read_text(encoding="utf-8")
    elif os.getenv("S3_ENABLED", "false").lower() == "true" and os.getenv("S3_BUCKET"):
        text = _read_manifest_from_s3(job_id)
    if text is None:
        return None
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _read_manifest_from_s3(job_id: str) -> str | None:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("s3", region_name=region)
        try:
            obj = client.get_object(
                Bucket=os.getenv("S3_BUCKET"), Key=f"manifests/{job_id}.jsonl"
            )
        except ClientError:
            return None
        return obj["Body"].read().decode("utf-8")
    except Exception:  # noqa: BLE001 — treat any S3 error as "no manifest"
        return None


@router.get("/results/{job_id}")
def get_results(job_id: str, user: dict = Depends(get_current_user)):
    """Structured classification results for a run: the relevant documents first."""
    entries = _load_manifest(job_id)
    if entries is None:
        # Not an error: the run may have had classification disabled or found
        # nothing. The frontend shows a friendly note.
        return {"job_id": job_id, "available": False, "counts": {}, "relevant": []}

    counts: dict[str, int] = {}
    relevant = []
    for idx, e in enumerate(entries):
        decision = e.get("decision", "")
        counts[decision] = counts.get(decision, 0) + 1
        if decision in _RELEVANT_DECISIONS:
            relevant.append(
                {
                    "index": idx,
                    "filename": e.get("filename", ""),
                    "hostname": e.get("hostname", ""),
                    "url": e.get("url", ""),
                    "score": e.get("module_handbook_score"),
                    "decision": decision,
                    "extraction_status": e.get("extraction_status", ""),
                }
            )
    # Highest score first; None scores (unreadable) sink to the bottom.
    relevant.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    counts["total"] = len(entries)
    return {"job_id": job_id, "available": True, "counts": counts, "relevant": relevant}


@router.get("/download/{job_id}/{index}")
def download_result(
    job_id: str, index: int, user: dict = Depends(get_current_user)
):
    """Download one scraped document by its manifest index (local file or S3)."""
    entries = _load_manifest(job_id)
    if entries is None or not (0 <= index < len(entries)):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    entry = entries[index]
    filename = entry.get("filename") or "document.pdf"

    # Local file (dev / EC2-local storage): serve directly, guarding against
    # path traversal by requiring the file to live under the output directory.
    saved_path = entry.get("saved_path")
    if saved_path:
        path = Path(saved_path)
        output_root = (Path(__file__).resolve().parent.parent.parent / "output").resolve()
        try:
            within = path.resolve().is_relative_to(output_root)
        except (OSError, ValueError):
            within = False
        if within and path.exists():
            return FileResponse(path, filename=filename, media_type="application/pdf")

    # Otherwise stream the object from S3 through the app (keeps the request
    # authenticated and avoids browser-side CORS on presigned URLs).
    s3_key = entry.get("s3_key")
    if s3_key and os.getenv("S3_BUCKET"):
        stream = _stream_s3(s3_key)
        if stream is not None:
            return StreamingResponse(
                stream,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    raise HTTPException(status_code=404, detail="Datei nicht verfügbar.")


def _stream_s3(key: str):
    """Return an iterator over an S3 object's bytes, or None if unavailable."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("s3", region_name=region)
        try:
            obj = client.get_object(Bucket=os.getenv("S3_BUCKET"), Key=key)
        except ClientError:
            return None
        return obj["Body"].iter_chunks(chunk_size=64 * 1024)
    except Exception:  # noqa: BLE001
        return None


@router.get("/log")
def get_log(user: dict = Depends(get_current_user)):
    """Return the log lines of the most recent scrape run only."""
    if not LOG_FILE.exists():
        return {"lines": []}
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    last_start = None
    for i, line in enumerate(lines):
        if line.startswith(RUN_MARKER):
            last_start = i
    if last_start is None:
        return {"lines": []}
    return {"lines": lines[last_start:]}
