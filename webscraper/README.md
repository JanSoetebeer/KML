# webscraper

A modular, ethical web scraper built on [Scrapy](https://scrapy.org/).  
Currently supports downloading PDF and Word documents from a given URL.  
Designed so new scraper types, storage backends, and AI pipelines can be added with minimal friction.

---

## Quick start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in the environment file
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux

# 4. Run
python run.py https://example.com/resources
```

Output files land in `output/<hostname>/<job_id>/`.  
A timestamped log is written to `logs/<job_id>.log`.

---

## CLI options

```
python run.py <url> [--job-id <id>] [--log-level DEBUG|INFO|WARNING] [--no-ping]
```

| Flag | Default | Description |
|---|---|---|
| `url` | *(required)* | Seed URL to scrape |
| `--job-id` | auto UUID | Custom run identifier |
| `--log-level` | `INFO` | Verbosity |
| `--no-ping` | off | Skip HEAD reachability check before crawling |

---

## Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `LOCAL_ENABLED` | `true` | Save files to `output/` |
| `S3_ENABLED` | `false` | Upload files to S3 |
| `S3_BUCKET` | — | S3 bucket name |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials |
| `AWS_DEFAULT_REGION` | `eu-central-1` | AWS region |
| `DOWNLOAD_DELAY` | `1` | Seconds between requests (ethical scraping) |
| `CONCURRENT_REQUESTS` | `4` | Parallel requests |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Project structure

```
webscraper/
├── run.py                          CLI entrypoint
├── lambda_handler.py               AWS Lambda stub
├── scrapy.cfg
├── requirements.txt
├── .env.example
│
├── webscraper/
│   ├── settings.py                 Feature flags, pipeline toggles, rate-limit config
│   ├── items.py                    DocumentItem definition
│   │
│   ├── validators/
│   │   └── url_validator.py        Scheme / DNS / reachability checks
│   │
│   ├── spiders/
│   │   ├── base_spider.py          Abstract base — all spiders inherit this
│   │   └── document_spider.py      Scrapes PDF / DOCX links from a seed URL
│   │
│   ├── pipelines/
│   │   ├── base_pipeline.py        Interface every pipeline must implement
│   │   ├── local_storage_pipeline.py
│   │   └── s3_pipeline.py
│   │
│   ├── middlewares/
│   │   └── polite_middleware.py    robots.txt, delay, user-agent enforcement
│   │
│   └── utils/
│       └── logging_config.py       File + console logging setup
│
├── logs/                           One .log file per run
└── output/                         Downloaded files (local storage)
```

---

## Adding a new spider

1. Create `webscraper/spiders/my_spider.py`.
2. Subclass `BaseSpider`.
3. Set a unique `name = "my_spider"`.
4. Implement `parse()`.
5. Done — Scrapy auto-discovers it. Invoke with `process.crawl(MySpider, ...)`.

## Adding a new pipeline

1. Create `webscraper/pipelines/my_pipeline.py`.
2. Subclass `BasePipeline`.
3. Implement `process_item()`.
4. Register it in `webscraper/settings.py` under `ITEM_PIPELINES` with a priority number.

---

## AWS Lambda deployment

See `lambda_handler.py` for the full deployment checklist and expected event payload.

```json
{
  "url": "https://example.com/resources",
  "job_id": "optional-custom-id",
  "log_level": "INFO"
}
```
