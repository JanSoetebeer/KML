"""Build the final, merged dataset from ALL runs.

Base = deep_run.jsonl (dedup by URL) + URLs only found by other runs. Overlays, in order (later wins):
  1. OCR re-processing (ocr*.jsonl)        -> new score / extraction_status
  2. LLM verdicts (llm_reviewed, llm_mid*, llm_pilot, llm_ocr) -> authoritative
Writes auswertung/data/final.jsonl with a `tier` per document:
  llm_confirmed        LLM says Modulhandbuch (confidence >= 0.8)
  llm_lowconf          LLM says yes but confidence < 0.8   (excluded from strict)
  llm_rejected         LLM says no
  tfidf_high           deep-run positive (score >= 0.9 after the LLM passes), never LLM-reviewed
  tfidf_other          positive from another run (Aug run / seed runs), never LLM-reviewed
  tfidf_negative       negative, never LLM-reviewed
  unresolved           still needs_review (no text / extraction failed / ocr no result)
"""
import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = 0.8


def rows(pattern):
    for f in sorted(glob.glob(str(ROOT / pattern))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def main():
    base = {r["url"]: r for r in rows("deep_run.jsonl")}
    for r in base.values():
        r["source_run"] = "deep_run"
    # Other runs only contribute URLs the deep run did not find (deep wins on overlap).
    # Precedence among the others: targeted seed/discovery runs before the August run.
    for name, src in [("seeds_only_run.jsonl", "seeds_only"), ("seeds_verified.jsonl", "seeds_verified"),
                      ("seeds_verified2.jsonl", "seeds_verified2"), ("run_full.jsonl", "run_full_aug")]:
        for r in rows(name):
            if r["url"] not in base:
                r["source_run"] = src
                base[r["url"]] = r
    n_ocr = 0
    for r in rows("ocr*.jsonl"):
        b = base.get(r["url"])
        if b is not None:
            b["module_handbook_score"] = r["module_handbook_score"]
            b["extraction_status"] = r["extraction_status"]
            b["decision"] = r["decision"]
            b["ocr_reprocessed"] = True
            n_ocr += 1
    llm_files = ["llm_reviewed.jsonl", "llm_mid*.jsonl", "llm_pilot.jsonl", "llm_ocr.jsonl", "llm_suspect*.jsonl"]
    n_llm = Counter()
    for pat in llm_files:
        for r in rows(pat):
            b = base.get(r["url"])
            if b is None:
                n_llm["not_in_any_run"] += 1
                continue
            for k in ("llm_is_match", "llm_spec", "llm_confidence", "llm_reason", "llm_model", "llm_reviewed"):
                if k in r:
                    b[k] = r[k]
            b["llm_batch"] = pat.replace("*", "")
            n_llm[pat] += 1
    tiers = Counter()
    out = ROOT / "auswertung/data/final.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for r in base.values():
            if r.get("llm_reviewed"):
                if r.get("llm_is_match"):
                    t = "llm_confirmed" if (r.get("llm_confidence") or 0) >= CONF else "llm_lowconf"
                else:
                    t = "llm_rejected"
            elif r["decision"] == "automatic_positive":
                t = "tfidf_high" if r["source_run"] == "deep_run" else "tfidf_other"
            elif r["decision"] == "automatic_negative":
                t = "tfidf_negative"
            else:
                t = "unresolved"
            r["tier"] = t
            tiers[t] += 1
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("docs:", len(base), "| ocr overlaid:", n_ocr, "| llm overlaid:", dict(n_llm))
    print(dict(tiers))


main()
