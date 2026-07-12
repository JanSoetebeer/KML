# Modulhandbuch Classifier

Binary document classifier for the webscraper: decides whether a downloaded file
is a **Modulhandbuch** (`1`) or **not** (`0`).

This is the TF-IDF + linear baseline recommended as the first productive stand:
fast, interpretable, cheap, and — crucially — easy to evaluate honestly. It is a
**standalone package**, decoupled from Scrapy, so it can be trained and tested on
a folder of labelled PDFs by itself. Wiring it into the crawler and webapp is a
separate step (see *Integration roadmap* below).

## Install

```bash
# from the repo root, into the repo-root .venv
.venv/Scripts/python -m pip install -r mlclassifier/requirements.txt
```

## Data layout

The labelled corpus lives under `modulhandbuecher/` (git-ignored), split into
`positiv/` and `negativ/`, each keeping **one sub-folder per university**:

```
modulhandbuecher/
├── positiv/<university_slug>/<name>__<hash>.pdf
└── negativ/<university_slug>/<name>__<hash>.pdf
```

The university sub-folder is essential: the train/test split is **grouped by
university** so a school is never in both train and test. That measures the hard,
realistic question — *does the model recognise Modulhandbücher from universities
it has never seen?* — instead of just re-recognising a familiar template.

## Usage

```bash
# Train, evaluate (grouped CV), and save the model + report.
.venv/Scripts/python -m mlclassifier train

# Classify one or more PDFs with the saved model.
.venv/Scripts/python -m mlclassifier predict path/to/file.pdf --json

# Only (re)build the extraction cache, e.g. after adding data.
.venv/Scripts/python -m mlclassifier build-dataset

# Add reviewed scraped documents to the training set (see feedback loop below).
.venv/Scripts/python -m mlclassifier ingest --manifest MANIFEST.jsonl --label positiv
.venv/Scripts/python -m mlclassifier ingest some/dir_or_file.pdf --label negativ
```

Artifacts are written to `mlclassifier/artifacts/`:
`module_classifier.joblib` (model + embedded metadata/thresholds) and
`training_report.json` (metrics for both feature variants).

## How it works

- **Extraction** (`extraction.py`): every file → one unified record
  `{text, title, page_count, extraction_status, …}`. A failed/scanned extraction
  is flagged, **never** silently treated as negative.
- **Dataset** (`dataset.py`): walks the label folders, caches extracted text
  (so re-training is fast), recovers the university group, and drops exact
  duplicates by normalised-text hash to prevent train/test leakage.
- **Features** (`features.py`): two comparable variants —
  - `content`: word + char TF-IDF over the document text (char n-grams add
    robustness to OCR/hyphenation noise);
  - `metadata`: the above **plus** filename, title and numeric document features.
- **Model** (`pipeline.py`): logistic regression (balanced classes) in one
  sklearn `Pipeline`, so vectorisers are fit only on training folds.
- **Training** (`train.py`): `StratifiedGroupKFold` by university → out-of-fold
  probabilities → PR-AUC / ROC-AUC / precision / recall / F1 / F2 + confusion
  matrix. Decision thresholds are **derived from the data** to hit the recall
  goal, not fixed at 0.5.
- **Prediction** (`predict.py`): 3-way decision —
  `score ≥ upper → automatic_positive`, `score ≤ lower → automatic_negative`,
  in-between → `needs_review` (the human-in-the-loop / active-learning band).

### Content vs. metadata — the leakage check

Both variants are trained and reported every run. A filename like
`Modulhandbuch.pdf` is a strong but potentially misleading signal (a
Prüfungsordnung can be named that way too). If `metadata` were *much* better than
`content`, the model would likely be reading filenames, not documents — the run
logs a warning. In the current data the two are ~equal, so the leaner, less-leaky
`content` model ships.

## Baseline results (grouped CV, unseen universities)

202 docs · 21 universities · 134 positive / 68 negative

| Variant | PR-AUC | ROC-AUC | Recall @target | Precision @target |
|---|---|---|---|---|
| **content** (shipped) | 0.957 | 0.941 | 0.955 | 0.871 |
| metadata | 0.960 | 0.926 | 0.955 | 0.848 |

Read these as *directional* — with only ~21 universities the estimates are
noisy. The next win is more (and harder) negatives and more universities.

## Scraper integration & feedback loop (built)

The scraper's `ClassificationPipeline` (enable with `CLASSIFIER_ENABLED=true`)
scores every downloaded document via this package's `Classifier.classify_bytes`
and writes a per-crawl review manifest to `webscraper/output/_review/`. The
`ingest` command closes the loop back to training:

```
scrape → classify → review manifest → (human review) → ingest → retrain
```

- `ingest --manifest <file> --label positiv|negativ [--decision needs_review]`
  copies manifest-listed files into `modulhandbuecher/<label>/<hostname>/`
  (hostname = group, mirroring the university grouping).
- `ingest <paths...> --label ... [--group NAME]` adds ad-hoc files/dirs.

See [`../webscraper/README.md`](../webscraper/README.md) → *Document classification*.

## Roadmap (next steps, not yet built)

1. **Model artifact in S3** — publish `module_classifier.joblib` to the existing
   bucket and load it at startup (`MODEL_PATH=s3://…` / synced file); register it
   in the webapp `SYS_AI_MODELS` registry so admins can manage the active version.
2. **Review UI** — surface the `needs_review` manifest in the webapp for one-click
   labelling instead of hand-editing, then trigger `ingest` + retrain.
3. **Threaded scoring** — move extraction/scoring off the crawl reactor thread so
   large PDFs don't block concurrent jobs.

## Limitations

- PDF-only extraction so far (the labelled set is 100% PDF). DOCX/HTML hooks are
  stubbed in `extraction.py` for a drop-in later.
- No OCR yet — fine here (0/16 sampled PDFs were scanned), but scanned positives
  would currently land in `needs_review` via the `empty_document` status.
- Small university count → treat metrics as a starting signal, not a final grade.
