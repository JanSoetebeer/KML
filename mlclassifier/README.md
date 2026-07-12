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

## Integration roadmap (next steps, not yet built)

1. **Scrapy pipeline** — a `ClassificationPipeline` that runs after download:
   extract text → `classify_document` → attach `{score, decision}` to the item /
   sidecar file. Slots into `ITEM_PIPELINES` next to the storage pipelines.
2. **Model artifact in S3** — publish `module_classifier.joblib` to the existing
   bucket and load it at startup; register it in the webapp `SYS_AI_MODELS`
   registry so admins can see/manage the active model version.
3. **Review queue / active learning** — persist `needs_review` documents; feed
   corrected labels back into `modulhandbuecher/` and retrain (spec §14).

## Limitations

- PDF-only extraction so far (the labelled set is 100% PDF). DOCX/HTML hooks are
  stubbed in `extraction.py` for a drop-in later.
- No OCR yet — fine here (0/16 sampled PDFs were scanned), but scanned positives
  would currently land in `needs_review` via the `empty_document` status.
- Small university count → treat metrics as a starting signal, not a final grade.
