# Smoke test — verify recall before the big harvest

Run the crawler against **4 universities with known Modulhandbuch locations**
(verified July 2026) and check how many we actually find, *before* committing a
run on the full list. Seeds: [`smoke-test-unis.txt`](../../../smoke-test-unis.txt)
(repo root). Costs a few cents, ~20–40 min.

## Ground truth (what a good run must find)

| University | Seed | A known Modulhandbuch URL | Structure it stresses |
|---|---|---|---|
| **FH Wedel** | `www.fh-wedel.de` | `www.fh-wedel.de/fileadmin/FHW-Files/Dokumente_FHW/Organisation/Modulhandbuecher/Bachelor_Informatik.pdf` | **Easy** — all on the main domain, one `/fileadmin/…/Modulhandbuecher/` folder |
| **TU Dortmund** | `www.tu-dortmund.de` | `cs.tu-dortmund.de/storages/cs/r/…/modulhandbuch-bsc-infak26.pdf` | **Faculty subdomain** + deep path + 156 programs (page-budget stress) |
| **RWTH Aachen** | `www.rwth-aachen.de` | `sc.informatik.rwth-aachen.de/wp-content/uploads/…/…BSInf.pdf` **and** `www.rwth-aachen.de/global/show_document.asp?id=…` | **Many faculty subdomains** + **script-served PDF** (no `.pdf` in the URL) |
| **FH Münster** | `www.fh-muenster.de` | `www.fh-muenster.de/eti/downloads/module/Modulhandbuch_Informatik_…pdf` | Subdomain-ish + `/downloads/…` document folder |

These four cover: the easy baseline, the faculty-subdomain case we built for, the
page-budget stress case, and the **known weakness** (script-served downloads).

## Script-served downloads — now handled (verify here)

RWTH's main-domain handbooks are served as `…/show_document.asp?id=aaaa…` — the
URL has **no `.pdf` extension**. Target detection now falls back to the fetched
response's **Content-Type** (`is_target_response`), so these are caught anyway
and stored with `file_type=pdf` (a hash-suffixed filename avoids collisions,
since such URLs differ only by query string). This also covers `download.php?id=`
and similar script endpoints.

This smoke test is the place to confirm it works end-to-end: expect RWTH's
`show_document.asp?id=…` handbooks to appear in the manifest as `.pdf`. (Still
out of reach: handbooks behind a login, generated on-the-fly by a course system
with no downloadable file, or on a *different registrable domain* than the seed.)

## Run it

Via the Actions tab (after the one-time setup + a push that built the image):

1. Upload the seed list:
   `aws s3 cp smoke-test-unis.txt s3://webscraper-output-660941536751/lists/smoke.txt --region eu-central-1`
2. **Actions → Bulk crawl (Fargate) → Run workflow**:
   - `urls_s3` = `s3://webscraper-output-660941536751/lists/smoke.txt`
   - `profile` = `modulhandbuch`
   - `max_pages` = **500** (give the big unis a fair shot for the test)
   - `max_depth` = `3`
3. Note the **batch id** the workflow prints, and watch:
   `aws logs tail /ecs/webscraper-bulk --follow --region eu-central-1`

## Measure recall

Pull the run's manifest and check what was found:

```bash
aws s3 cp s3://webscraper-output-660941536751/manifests/<batch_id>.jsonl smoke.jsonl --region eu-central-1
```

Documents found per university host:

```bash
python -c "import json,collections;c=collections.Counter(json.loads(l)['hostname'] for l in open('smoke.jsonl'));[print(f'{n:4} {h}') for h,n in c.most_common()]"
```

Did we hit the known ground-truth files? (distinctive filename tokens):

```bash
grep -iE 'Bachelor_Informatik\.pdf|modulhandbuch-bsc-inf|BSInf|Modulhandbuch_Informatik' smoke.jsonl
```

What the model judged a Modulhandbuch (the review-worthy ones):

```bash
python -c "import json,collections;c=collections.Counter(json.loads(l)['decision'] for l in open('smoke.jsonl'));print(dict(c))"
```

You can also open the run in the webapp (it's under the smoke `batch_id`) to see
the review view.

## Reading the result

- **FH Wedel** should be ~complete (easy case). If it isn't, the crawl isn't
  reaching `/fileadmin/…/Modulhandbuecher/` — investigate first.
- **TU Dortmund / RWTH** partial is expected on the first pass; note *how* partial.
  Subdomain PDFs (sc.informatik, cs.tu-dortmund) confirm faculty-following;
  `show_document.asp?id=…` entries appearing as `.pdf` confirm Content-Type
  detection.
- Then we tune: raise `CRAWL_MAX_PAGES` / `CRAWL_MAX_SUBDOMAIN_SITEMAPS` *before*
  the full harvest based on where recall fell short.

Re-running is cheap and safe: the DynamoDB visited store skips done seeds unless
`BULK_FORCE=true`, and S3 output is just a prefix you can delete.
