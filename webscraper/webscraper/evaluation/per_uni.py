"""
Per-university diagnostics — the manual-worklist + targeted-re-run companion to
the aggregate evaluation report.

The aggregate report (``report.py``) answers *how well did the run do overall*.
This module answers the operational question: **for each university, what (if
anything) is wrong, and what should I do about it** — which unis returned 0/few
handbooks, which look like they need JavaScript rendering or are robots-blocked,
and which are simply candidates for a manual download.

It joins three things per registered domain:

* the crawl outcome (docs / positives / review / negative) — from the evaluation;
* optionally, the **discovery seeds** found for the domain (a discovered-URL
  JSONL, see :mod:`webscraper.discovery`) and how many of those seed URLs
  actually made it into the manifest — the gap between *found* and *downloaded*
  is the tell-tale of a robots-block or JS-gated site;

and derives a single ``flag`` + human ``action`` per university.

Output is a CSV (one row per university, worst-first) you can open in Excel as a
work list, plus the same rows as JSON. Purely stdlib.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from webscraper.evaluation.evaluate import registered_domain

# Flag → human-readable action. The flags are ordered by how actionable they are;
# ``_flag_for`` returns the first that matches so each uni gets one clear verdict.
FLAG_ACTIONS = {
    "no_docs_no_seeds": "Nichts gefunden — Discovery erweitern (Serper/Firecrawl) "
                        "oder Modulhandbuch-Standort manuell suchen & laden.",
    "seeds_found_0_downloaded": "Discovery fand URLs, Crawl lud 0 → robots.txt-Sperre "
                                "ODER JS-gated. JS-Render testen; sonst manuell laden.",
    "seeds_underfetched": "Nur ein Teil der Discovery-URLs geladen → robots/JS "
                          "teilweise; Rest ggf. manuell laden.",
    "no_positive": "Dokumente da, aber 0 als Modulhandbuch erkannt → Schwelle/LLM-"
                   "Review prüfen; ggf. manuell verifizieren.",
    "low_recall": "Wenige Modulhandbücher — Discovery/JS-Render versuchen, "
                  "sonst Rest manuell.",
    "ok": "OK — keine Aktion nötig.",
}


def _norm_url(url: str) -> str:
    """Normalise a URL for matching a discovery seed against a manifest entry:
    lower-case scheme+host, strip a single trailing slash and any fragment."""
    p = urlparse((url or "").strip())
    path = p.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    host = (p.netloc or "").lower()
    return f"{p.scheme.lower()}://{host}{path}" + (f"?{p.query}" if p.query else "")


def _flag_for(docs: int, positive: int, seeds: int, downloaded: int,
              low_recall: int) -> str:
    """Pick the single most-actionable flag for one university."""
    if docs == 0:
        if seeds > 0:
            return "seeds_found_0_downloaded"
        return "no_docs_no_seeds"
    # docs > 0 from here
    if seeds > 0 and downloaded == 0:
        # We did crawl the site (docs > 0) but none of the discovered deep URLs
        # came through — those specific handbooks are blocked/JS-gated.
        return "seeds_found_0_downloaded"
    if positive == 0:
        return "no_positive"
    if seeds > downloaded > 0:
        return "seeds_underfetched"
    if positive < low_recall:
        return "low_recall"
    return "ok"


def build_per_uni_rows(
    ev,
    records: Optional[list[dict]] = None,
    discovery_seeds: Optional[dict[str, list[str]]] = None,
    low_recall: int = 3,
) -> list[dict]:
    """Build one diagnostic row per (distinct-domain) university in the CSV.

    ``records`` is the manifest record list (defaults to the ones stashed on
    ``ev`` by :func:`build_evaluation`). ``discovery_seeds`` is a
    ``{base_domain: [urls]}`` map (from :func:`webscraper.discovery.load_discovery_seeds`);
    when given, each row reports how many seeds were found for the domain and how
    many of them appear in the manifest. ``low_recall`` is the positive-count
    below which a uni is flagged for a discovery/JS retry.
    """
    if records is None:
        records = getattr(ev, "_records", [])
    discovery_seeds = discovery_seeds or {}

    # Manifest URLs grouped by registered domain — for the seed cross-reference.
    dl_by_domain: dict[str, set[str]] = {}
    for r in records:
        dom = registered_domain(r.get("hostname", ""))
        dl_by_domain.setdefault(dom, set()).add(_norm_url(r.get("url", "")))

    rows: list[dict] = []
    for u in ev.universities:
        if u.is_duplicate_domain:
            continue  # folded into the row that owns the domain
        m = u.metrics
        seed_urls = discovery_seeds.get(u.domain, [])
        seeds = len(seed_urls)
        downloaded_urls = dl_by_domain.get(u.domain, set())
        downloaded = sum(1 for s in seed_urls if _norm_url(s) in downloaded_urls)

        flag = _flag_for(m.docs_total, m.mh_positive, seeds, downloaded, low_recall)
        rows.append({
            "csv_id": u.csv_id,
            "short_name": u.short_name,
            "name": u.name,
            "domain": u.domain,
            "uni_type": u.uni_type,
            "traeger": u.traeger,
            "bundesland": u.bundesland,
            "students": u.students if u.students is not None else "",
            "docs_total": m.docs_total,
            "mh_positive": m.mh_positive,
            "mh_review": m.mh_review,
            "mh_negative": m.mh_negative,
            "discovery_seeds": seeds,
            "discovery_downloaded": downloaded,
            "flag": flag,
            "action": FLAG_ACTIONS.get(flag, ""),
            "hostnames": " ".join(u.hostnames),
            "seed_url": u.seed_url,
        })

    # Worst-first so the work list starts at the biggest gaps: 0-doc unis, then
    # 0-positive, then low recall; "ok" rows sink to the bottom.
    flag_rank = {
        "no_docs_no_seeds": 0, "seeds_found_0_downloaded": 1, "no_positive": 2,
        "seeds_underfetched": 3, "low_recall": 4, "ok": 5,
    }
    rows.sort(key=lambda r: (flag_rank.get(r["flag"], 9), r["mh_positive"],
                             r["docs_total"]))
    return rows


def summarize_rows(rows: list[dict]) -> dict[str, int]:
    """Count universities per flag — a one-line health summary for stderr."""
    out: dict[str, int] = {}
    for r in rows:
        out[r["flag"]] = out.get(r["flag"], 0) + 1
    return out


def write_per_uni_csv(rows: list[dict], path: str | Path) -> None:
    """Write the diagnostic rows to a CSV (UTF-8 with BOM so Excel opens it clean)."""
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_per_uni_json(rows: list[dict], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
