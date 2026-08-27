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

# BEST recall — Serper (Google index, reaches deep files CC misses) UNIONED with
# Common Crawl. Needs SERPER_API_KEY in the env (see below).
SERPER_API_KEY=sk-... python -m webscraper.discovery --csv "..." \
    --provider serper commoncrawl --out discovered.jsonl

# Quick sanity check on the first 10 domains
python -m webscraper.discovery --csv "..." --provider commoncrawl --limit 10 --out /tmp/probe.jsonl
```

Passing several `--provider` names unions their results per domain (dedup).

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
| `google` | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | Deprecated for us — Google removed whole-web Programmable Search (50-domain cap). Kept for completeness. |
| `serper` | `SERPER_API_KEY` | **Recommended paid option.** Google's real index via serper.dev — reaches the deep unlinked handbooks (Konstanz `modulebook`) CC misses. $1 / 1,000 queries, 2,500 free credits on signup. Best `--provider serper commoncrawl`. |
| `firecrawl` | `FIRECRAWL_API_KEY` | JS-rendering site map (`/map`) — finds document links hidden behind JavaScript that a static fetch never sees. For JS-heavy sites that returned 0. Free tier 1,000 credits/mo, then ~$0.001/page. |

### Serper setup

1. Sign up at [serper.dev](https://serper.dev/) (2,500 free credits).
2. Copy your API key from the dashboard.
3. Export it when running discovery: `SERPER_API_KEY=sk-... python -m webscraper.discovery …`
   (discovery is an offline local step, so the key lives in your shell/`.env`, not in AWS).

### Google Custom Search setup

1. Create a Google Cloud project.
2. Enable the **Custom Search API** (`customsearch.googleapis.com`).
3. Create an **API key** → `GOOGLE_API_KEY`.
4. Create a Programmable Search Engine (programmablesearchengine.google.com) set
   to **"Search the entire web"**; copy its **Search engine ID (cx)** →
   `GOOGLE_CSE_ID`.
5. Run with `--provider google` (reads both from the environment).

~400 domains × ~2 queries ≈ 800 queries ≈ $4 one-off, or 100/day for free.

### Firecrawl setup

1. Sign up at [firecrawl.dev](https://firecrawl.dev/) (free tier: 1,000 credits/mo).
2. Export the key: `FIRECRAWL_API_KEY=fc-... python -m webscraper.discovery … --provider firecrawl`.

## Reusing discovery for another use case

Discovery is **profile-driven** — nothing here is hard-coded to Modulhandbücher.
The active `--profile` (a `webscraper.profiles.ExtractionProfile`) supplies both
the search phrases and the URL stems, so a new document type or a completely
different use case (e.g. news articles) plugs in with no changes to this package:

```python
# webscraper/profiles/news.py
class NewsProfile(KeywordScoredProfile):
    name = "news"
    discovery_terms = ("nachrichten", "pressemitteilung", "news article")
    discovery_url_stems = ("news", "artikel", "presse", "/20")   # what a news URL looks like
```

Then `python -m webscraper.discovery --csv sites.csv --profile news --provider serper commoncrawl`.
The matching LLM-review criteria live alongside, as a `ClassificationSpec` in
`mlclassifier/specs.py` (`--spec news_article`). One use case, described once,
reused across crawl → discovery → review.

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
