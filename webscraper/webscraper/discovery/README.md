# Search-discovery (search-engine seeding)

Find Modulhandbuch document URLs with a **search engine** and feed them to the
crawl as high-priority seeds. This closes the two biggest recall gaps seen in the
411-university run: universities where the crawl downloaded **0 documents** (the
handbooks exist but sit behind JS / a search box / too deep for the page budget)
and universities with **low per-uni recall** (the crawl ran out of budget before
reaching all handbooks). Discovery runs *outside* Scrapy — search endpoints would
be blocked by `ROBOTSTXT_OBEY` — as a batch pre-step that emits a URL list.

## 1. Discover (produces `discovered.jsonl`)

```bash
cd webscraper

# Free, no key — Common Crawl (bulk, un-throttled; index lags a few months)
python -m webscraper.discovery --csv "../hs_liste_ready_for_import 1.csv" \
    --provider commoncrawl --out discovered.jsonl

# Quick sanity check on the first 10 domains
python -m webscraper.discovery --csv "..." --provider commoncrawl --limit 10 --out /tmp/probe.jsonl
```

Output is one JSON object per line: `{"domain": "...", "url": "..."}`.

## 2. Crawl with the discovered seeds

Point the crawl at the file; each job seeds its domain's URLs as targets
(downloaded + classified above the normal frontier). Unset ⇒ normal crawl.

```bash
DISCOVERY_SEEDS_PATH=discovered.jsonl python run.py --urls-file seeds.txt --profile modulhandbuch
```

For the Fargate bulk run, set `DISCOVERY_SEEDS_PATH` in the task definition (stage
the file into the image or `/tmp` first).

## Providers

| provider | key needed | notes |
|---|---|---|
| `commoncrawl` | none | Free. Public index hosted in AWS S3. Bulk-friendly. Recovered handbooks for ~60% of failing domains in testing — strong on faculty / module-DB subdomains (`moduldb.htwsaar.de`), blind to the deepest *unlinked* files (it link-crawls too). |
| `duckduckgo` | none | Free, fresh — but the HTML endpoint serves an anti-bot CAPTCHA under load, so it is unreliable for batch use. |
| `google` | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | Highest quality; has the deep unlinked handbooks Common Crawl misses. 100 queries/day free, then $5/1,000. |

### Google Custom Search setup

1. Create a Google Cloud project.
2. Enable the **Custom Search API** (`customsearch.googleapis.com`).
3. Create an **API key** → `GOOGLE_API_KEY`.
4. Create a Programmable Search Engine (programmablesearchengine.google.com) set
   to **"Search the entire web"**; copy its **Search engine ID (cx)** →
   `GOOGLE_CSE_ID`.
5. Run with `--provider google` (reads both from the environment).

~400 domains × ~2 queries ≈ 800 queries ≈ $4 one-off, or 100/day for free.

## How it fits together

```
CSV of universities ──► discovery (this package) ──► discovered.jsonl
                                                          │
                          DISCOVERY_SEEDS_PATH ───────────┘
                                                          ▼
                        run.py / bulk_run.py ──► JobRunner ──► DocumentSpider
                                                   (per-domain extra_seeds,
                                                    fetched as priority targets)
```

Pure stdlib (`urllib`, `json`, `re`) — no third-party HTTP client — so it runs
anywhere the scraper runs.
