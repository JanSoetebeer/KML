"""Streamt Objekte aus S3 direkt in ein DataHub-Projekt, ohne sie lokal abzulegen.

Jedes Objekt wird aus S3 in den Arbeitsspeicher gelesen und per vorsignierter URL an den DataHub
geschickt. Grosse Objekte (> 100 MB) gehen als Multipart-Upload in 10-MB-Teilen, die per
Range-Request aus S3 geholt werden. Abgeschlossene Schluessel stehen in einer Statusdatei, ein
erneuter Start setzt dort fort.

Der API-Schluessel kommt aus der Umgebungsvariable DATAHUB_API_KEY (Seite /keys im DataHub), nie als Argument.

Beispiele (aus dem Repo-Root, AWS-Zugang muss gesetzt sein):

    set DATAHUB_API_KEY=...                                    (Windows: set, PowerShell: $env:DATAHUB_API_KEY=...)
    .venv\\Scripts\\python auswertung\\s3_to_datahub.py --list-projects
    .venv\\Scripts\\python auswertung\\s3_to_datahub.py --project-id 7 --bucket webscraper-output-081757578883 --prefix manifests/ --dry-run
    .venv\\Scripts\\python auswertung\\s3_to_datahub.py --project-id 7 --bucket webscraper-output-081757578883 --prefix manifests/
    .venv\\Scripts\\python auswertung\\s3_to_datahub.py --project-id 7 --bucket ... --prefix scraped/ --workers 16

Hinter dem Firmenproxy fuer AWS: --no-verify-ssl (gilt nur fuer S3, nicht fuer den DataHub).
"""
import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

PART = 10 * 1024 * 1024
BIG = 100 * 1024 * 1024


def api(session, host, method, path, **kw):
    for attempt in range(4):
        r = session.request(method, host + path, timeout=60, **kw)
        if r.status_code < 500 and r.status_code != 429:
            break
        time.sleep(2 ** attempt)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def put_bytes(url, data):
    last = None
    for attempt in range(4):
        try:
            r = requests.put(url, data=data, timeout=600)  # vorsigniert: kein Authorization-Header
            if r.status_code < 300:
                return r.headers.get("ETag", "").strip('"')
            last = f"{r.status_code} {r.text[:200]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"PUT fehlgeschlagen: {last}")


def upload_small(s3, session, host, pid, bucket, key, dest):
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    url = api(session, host, "POST", f"/api/projects/{pid}/upload", json={"path": dest})["url"]
    put_bytes(url, body)
    return len(body)


def upload_multipart(s3, session, host, pid, bucket, key, dest, size):
    up = api(session, host, "POST", f"/api/projects/{pid}/multipart", json={"path": dest})
    upload_id = up["upload_id"]
    parts, n, sent = [], 0, 0
    try:
        while sent < size:
            n += 1
            end = min(sent + PART, size) - 1
            data = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes={sent}-{end}")["Body"].read()
            urls = api(session, host, "POST", f"/api/projects/{pid}/multipart/parts",
                       json={"path": dest, "upload_id": upload_id, "part_numbers": [n]})
            url = _first_url(urls, n)
            parts.append({"part_number": n, "etag": put_bytes(url, data)})
            sent = end + 1
        api(session, host, "POST", f"/api/projects/{pid}/multipart/complete",
            json={"path": dest, "upload_id": upload_id, "parts": parts})
    except Exception:
        try:
            api(session, host, "POST", f"/api/projects/{pid}/multipart/abort",
                json={"path": dest, "upload_id": upload_id})
        finally:
            raise
    return size


def _first_url(resp, n):
    """Die Antwort nennt je Teil eine URL; Feldnamen defensiv lesen."""
    items = resp.get("parts") or resp.get("urls") or resp.get("items") or []
    if isinstance(items, dict):
        return items.get(str(n)) or next(iter(items.values()))
    it = items[0]
    return it["url"] if isinstance(it, dict) else it


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="https://datahub.kiwit-it.de")
    ap.add_argument("--project-id", type=int)
    ap.add_argument("--list-projects", action="store_true")
    ap.add_argument("--bucket")
    ap.add_argument("--prefix", action="append", default=[], help="S3-Praefix, mehrfach moeglich")
    ap.add_argument("--keys-file", help="Textdatei mit S3-Schluesseln (einer je Zeile) statt --prefix")
    ap.add_argument("--dest-prefix", default="s3/", help="Praefix im DataHub-Projekt (Standard: s3/)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="nur die ersten N Objekte (Test)")
    ap.add_argument("--region", default="eu-central-1")
    ap.add_argument("--no-verify-ssl", action="store_true")
    ap.add_argument("--state", default="auswertung/.datahub_uploaded.txt")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key_env = os.environ.get("DATAHUB_API_KEY")
    if not key_env:
        sys.exit("DATAHUB_API_KEY fehlt (Umgebungsvariable setzen, Schluessel nicht als Argument uebergeben).")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {key_env}"

    if a.list_projects:
        for p in api(session, a.host, "GET", "/api/projects"):
            print(p["id"], p.get("slug"), "|", p.get("name"), "| read_only =", p.get("read_only"))
        return
    if not (a.project_id and a.bucket and (a.prefix or a.keys_file)):
        sys.exit("--project-id, --bucket und --prefix (oder --keys-file) sind noetig.")

    s3 = boto3.client("s3", region_name=a.region, verify=not a.no_verify_ssl)
    objs = []
    if a.keys_file:
        for line in open(a.keys_file, encoding="utf-8"):
            k = line.strip()
            if k:
                objs.append((k, s3.head_object(Bucket=a.bucket, Key=k)["ContentLength"]))
    else:
        for pre in a.prefix:
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=a.bucket, Prefix=pre):
                objs += [(o["Key"], o["Size"]) for o in page.get("Contents", []) if not o["Key"].endswith("/")]
    if a.limit:
        objs = objs[: a.limit]

    done = set()
    if os.path.exists(a.state):
        done = {l.strip() for l in open(a.state, encoding="utf-8")}
    todo = [(k, s) for k, s in objs if k not in done]
    total = sum(s for _, s in todo)
    print(f"{len(objs)} Objekte gefunden, {len(todo)} offen ({total / 1e9:.2f} GB), Ziel: {a.dest_prefix}")
    if a.dry_run:
        for k, s in todo[:10]:
            print("  ", k, s)
        return

    lock = threading.Lock()
    stats = {"n": 0, "bytes": 0, "err": 0}
    t0 = time.time()
    state = open(a.state, "a", encoding="utf-8")
    failed = open(a.state + ".failed", "a", encoding="utf-8")

    def work(item):
        k, s = item
        dest = a.dest_prefix + k
        if s > BIG:
            upload_multipart(s3, session, a.host, a.project_id, a.bucket, k, dest, s)
        else:
            upload_small(s3, session, a.host, a.project_id, a.bucket, k, dest)
        return k, s

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for f in as_completed(futs):
            k, s = futs[f]
            with lock:
                try:
                    f.result()
                    state.write(k + "\n"); state.flush()
                    stats["n"] += 1; stats["bytes"] += s
                except Exception as e:  # einzelne Fehler stoppen den Lauf nicht
                    stats["err"] += 1
                    failed.write(f"{k}\t{e}\n"); failed.flush()
                if (stats["n"] + stats["err"]) % 200 == 0:
                    el = time.time() - t0
                    print(f"{stats['n']}/{len(todo)} ok, {stats['err']} Fehler, {stats['bytes'] / 1e9:.2f} GB, "
                          f"{stats['bytes'] / 1e6 / max(el, 1):.1f} MB/s", flush=True)
    print(f"Fertig: {stats['n']} hochgeladen, {stats['err']} Fehler ({a.state}.failed). Erneut starten setzt fort.")


if __name__ == "__main__":
    main()
