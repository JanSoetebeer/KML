"""
Extract seed URLs from uploaded / provided files (CSV, HTML, plain text).

Shared by both entry points so they behave identically:
- ``run.py`` (CLI ``--urls-file``)
- the web app's scrape router (uploaded file)

CSV handling is column-aware. Real-world lists (like the German university export
``hs_liste_ready_for_import.csv``) carry the URL in a named column such as
``Home Page`` / ``final_url`` — *not* the first column (which is an id). Naively
taking the first field would seed the crawl with row numbers. So we:

1. prefer a known URL-bearing column by header name, then
2. fall back to the first ``http(s)`` cell in each row.

Header rows and non-URL cells are skipped naturally because only ``http(s)``
values are accepted.
"""

from __future__ import annotations

import csv
import io

# Header names that carry a usable URL, most-preferred first.
_URL_HEADERS = (
    "final_url", "home page", "homepage", "url", "website", "webseite",
    "web", "link", "home",
)


def _is_url(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_urls_from_csv_text(text: str) -> list[str]:
    """Pull seed URLs from CSV text (column-aware, header-tolerant)."""
    try:
        delimiter = csv.Sniffer().sniff(
            "\n".join(text.splitlines()[:20]), delimiters=",;\t"
        ).delimiter
    except csv.Error:
        delimiter = ","

    rows = [
        row for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if row and not (len(row) == 1 and row[0].strip().startswith("#"))
    ]
    if not rows:
        return []

    # Detect a URL column from the header (only if the first row isn't data).
    header = [c.strip().lower() for c in rows[0]]
    header_has_url_value = any(_is_url(c) for c in rows[0])
    url_col: int | None = None
    if not header_has_url_value:
        for name in _URL_HEADERS:
            if name in header:
                url_col = header.index(name)
                break
        data_rows = rows[1:]
    else:
        data_rows = rows  # first row is data, not a header

    urls: list[str] = []
    for row in data_rows:
        value = ""
        if url_col is not None and url_col < len(row) and _is_url(row[url_col]):
            value = row[url_col].strip()
        else:
            value = next((c.strip() for c in row if _is_url(c)), "")
        if value:
            urls.append(value)
    return _dedupe(urls)


def extract_urls_from_html_text(text: str) -> list[str]:
    """Pull absolute http(s) links out of HTML text."""
    from parsel import Selector

    sel = Selector(text=text)
    urls: list[str] = []
    for attr in ("a::attr(href)", "link::attr(href)"):
        for href in sel.css(attr).getall():
            if _is_url(href or ""):
                urls.append(href.strip())
    return _dedupe(urls)


def extract_urls_from_text_lines(text: str) -> list[str]:
    """One URL per line; '#' comments and blanks ignored (plain .txt lists)."""
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return _dedupe(urls)
