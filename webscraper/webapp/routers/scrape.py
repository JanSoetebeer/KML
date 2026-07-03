"""
Scraping endpoints (Abschnitt 1).

- Exposes the grouped file-type catalogue (Dokument / Bild / Media).
- Lists the AI models the current user may choose (based on their roles).
- Triggers a scrape by invoking the deployed AWS Lambda function with the
  selected URLs + file types, and records each run in a local ``Log.txt``.
- Returns the current run's log section for the UI viewer.

Notes
-----
The AI model selection is a *gating requirement* only (no real ML processing
yet). The Lambda call uses boto3; configure ``LAMBDA_FUNCTION_NAME`` and a
region (``AWS_REGION`` / ``AWS_DEFAULT_REGION``) in the environment. Credentials
come from the standard AWS chain.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import get_current_user
from ..db import get_connection

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

# Project root (scrape.py -> routers -> webapp -> project root) holds Log.txt.
# Overridable via LOG_FILE so it can live on a persistent volume in Docker.
LOG_FILE = Path(
    os.getenv("LOG_FILE", str(Path(__file__).resolve().parent.parent.parent / "Log.txt"))
)

RUN_MARKER = "===== SCRAPE RUN"

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


def _extract_urls_from_html(text: str) -> list[str]:
    """Pull absolute http(s) links out of an uploaded HTML file."""
    from parsel import Selector

    sel = Selector(text=text)
    urls: list[str] = []
    for attr in ("a::attr(href)", "link::attr(href)"):
        for href in sel.css(attr).getall():
            href = (href or "").strip()
            if href.startswith(("http://", "https://")):
                urls.append(href)
    return urls


def _extract_urls_from_csv(text: str) -> list[str]:
    """One URL per line; first comma-separated field; '#' comments ignored."""
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        first = line.split(",")[0].strip()
        if first:
            urls.append(first)
    return urls


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _append_log(lines: list[str]) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def _invoke_lambda(payload: dict) -> tuple[bool, str]:
    """Invoke the deployed Lambda synchronously. Returns (ok, detail)."""
    function_name = os.getenv("LAMBDA_FUNCTION_NAME")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
    if not function_name:
        return False, "LAMBDA_FUNCTION_NAME ist nicht konfiguriert."

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
            return False, f"Lambda-Fehler ({status}): {body}"
        return True, f"Lambda-Antwort ({status}): {body}"
    except Exception as exc:  # noqa: BLE001 — surface any AWS/boto error to the log
        return False, f"Aufruf fehlgeschlagen: {exc}"


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
        raw = file.file.read().decode("utf-8", errors="replace")
        name = file.filename.lower()
        if name.endswith(".csv"):
            urls += _extract_urls_from_csv(raw)
        elif name.endswith((".html", ".htm")):
            urls += _extract_urls_from_html(raw)
        else:
            raise HTTPException(
                status_code=400, detail="Nur .csv oder .html Dateien werden unterstützt."
            )

    urls = _dedupe(urls)
    if not urls:
        raise HTTPException(
            status_code=400,
            detail="Keine URL angegeben bzw. keine URLs in der Datei gefunden.",
        )

    # --- invoke Lambda + log ---------------------------------------------
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload = {"urls": urls, "file_types": selected, "job_id": job_id}

    _append_log(
        [
            f"{RUN_MARKER} {now} | job={job_id} =====",
            f"Benutzer: {user['username']} ({user['position']})",
            f"KI-Modell: {model_label}",
            f"Dateiformate: {', '.join(selected)}",
            f"URLs ({len(urls)}): {', '.join(urls)}",
            "Starte Scrape via AWS Lambda…",
        ]
    )

    ok, detail = _invoke_lambda(payload)
    _append_log([detail, "Lauf beendet." if ok else "Lauf mit Fehler beendet."])

    return {
        "job_id": job_id,
        "ok": ok,
        "urls": urls,
        "file_types": selected,
        "detail": detail,
    }


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
