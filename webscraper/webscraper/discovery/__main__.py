"""
CLI: discover Modulhandbuch document URLs for a list of universities via a
search provider, and write them as JSONL for the crawl to consume as seeds.

Usage
-----
    # free, no key — Common Crawl (bulk) or DuckDuckGo (fresh)
    python -m webscraper.discovery --csv "../hs_liste_ready_for_import 1.csv" \
        --provider commoncrawl --out discovered.jsonl

    # Google Custom Search (needs GOOGLE_API_KEY + GOOGLE_CSE_ID in the env)
    python -m webscraper.discovery --csv "..." --provider google --out discovered.jsonl

Output: one JSON object per line — ``{"domain": "...", "url": "..."}`` — plus a
summary to stderr. ``--limit N`` restricts to the first N domains (handy for a
quick provider sanity check before a full run).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Load API keys (SERPER_API_KEY / FIRECRAWL_API_KEY) from webscraper/.env — run
# from the webscraper/ directory as documented, so cwd/.env is that file.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from webscraper.discovery.discover import (
    discover_for_domains,
    domains_from_urls,
    summarize,
)
from webscraper.discovery.providers import UnionProvider, get_provider
from webscraper.utils.url_sources import extract_urls_from_csv_text


def _read_domains(args) -> list[str]:
    if args.domains:
        return domains_from_urls(args.domains)
    text = Path(args.csv).read_text(encoding="utf-8", errors="replace")
    return domains_from_urls(extract_urls_from_csv_text(text))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m webscraper.discovery",
        description="Discover Modulhandbuch document URLs via a search provider.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="university seed list (Hochschul-CSV)")
    src.add_argument("--domains", nargs="+", help="explicit domains (skip the CSV)")
    ap.add_argument("--provider", nargs="+", default=["commoncrawl"],
                    choices=["commoncrawl", "duckduckgo", "google", "serper", "firecrawl"],
                    help="one or more providers; multiple are unioned per domain "
                         "(e.g. --provider serper commoncrawl)")
    ap.add_argument("--profile", default="modulhandbuch",
                    help="extraction profile whose discovery terms + URL stems to "
                         "use (webscraper/profiles/). Swap it to discover a "
                         "different document type / use case.")
    ap.add_argument("--terms", nargs="+", default=None,
                    help="override the profile's search terms")
    ap.add_argument("--max-results", type=int, default=25,
                    help="max document URLs to keep per domain")
    ap.add_argument("--cc-indexes", type=int, default=3,
                    help="commoncrawl: how many recent monthly snapshots to union "
                         "(more = higher recall, slower; default 3)")
    ap.add_argument("--serper-num", type=int, default=10,
                    help="serper: results per query (free tier max 10; a PAID plan "
                         "allows up to 100 — set 100 for far more PDFs per uni)")
    ap.add_argument("--serper-filetype", action="store_true",
                    help="serper: add 'filetype:pdf' to queries (PAID plans only — "
                         "the free tier 400s on site:+filetype:)")
    ap.add_argument("--delay", type=float, default=None,
                    help="seconds between queries (default: provider-specific)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N domains (0 = all)")
    ap.add_argument("--out", default="discovered.jsonl", help="output JSONL path")
    args = ap.parse_args(argv)

    domains = _read_domains(args)
    if args.limit:
        domains = domains[: args.limit]
    if not domains:
        print("error: no domains resolved from input", file=sys.stderr)
        return 2

    # The active profile supplies the use-case knowledge: search phrases and the
    # URL stems for client-side filtering. Swapping --profile is all it takes to
    # discover a different document type.
    from webscraper.profiles import get_profile

    profile = get_profile(args.profile)
    terms = args.terms or list(getattr(profile, "discovery_terms", ())) or None
    url_stems = getattr(profile, "discovery_url_stems", ()) or None

    # Common Crawl throttles bursts (drops the connection); a small gap plus the
    # built-in retries keeps a large batch flowing. DuckDuckGo needs a bigger gap.
    _default_delay = {"commoncrawl": 0.5, "duckduckgo": 3.0, "google": 0.2,
                      "serper": 0.2, "firecrawl": 0.2}
    built = []
    for name in args.provider:
        delay = args.delay if args.delay is not None else _default_delay.get(name, 0.5)
        built.append(get_provider(
            name,
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            cse_id=os.getenv("GOOGLE_CSE_ID", ""),
            serper_key=os.getenv("SERPER_API_KEY", ""),
            firecrawl_key=os.getenv("FIRECRAWL_API_KEY", ""),
            serper_num=args.serper_num,
            serper_filetype=args.serper_filetype,
            per_query_delay=delay,
            max_results=args.max_results,
            indexes=args.cc_indexes,
            url_stems=url_stems,
        ))
    provider = built[0] if len(built) == 1 else UnionProvider(built, max_results=args.max_results)

    print(f"Discovering over {len(domains)} domain(s) via {'+'.join(args.provider)} "
          f"(profile={args.profile}) …", file=sys.stderr)
    results = discover_for_domains(domains, provider, terms=terms)

    with open(args.out, "w", encoding="utf-8") as fh:
        for domain, urls in results.items():
            for url in urls:
                fh.write(json.dumps({"domain": domain, "url": url},
                                    ensure_ascii=False) + "\n")

    s = summarize(results)
    print(f"  domains with hits: {s['domains_with_hits']}/{s['domains']} "
          f"({s['coverage_rate']*100:.0f}%)  |  total URLs: {s['total_urls']}  "
          f"|  mean/domain: {s['urls_per_domain_mean']}", file=sys.stderr)
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
