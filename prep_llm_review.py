"""Build the review worklists from the last deep run (deep_run.jsonl) only.

Base = deep_run.jsonl, deduplicated by URL. Earlier LLM verdicts (llm_reviewed.jsonl)
are overlaid by URL onto the deep record (llm_* fields + decision), so nothing is
reviewed twice and older runs contribute nothing else. Deep-run records keep their
own s3_key.

Subsets are written with decision="needs_review" so `mlclassifier.llm_review`
(default --band needs_review) and `mlclassifier.reprocess_ocr` pick them up; the
tool output then carries the real decision. Optional trailing arg N splits a
subset into N shards (<name>.partK.jsonl) for parallel runs.

    python prep_llm_review.py base                   # -> base.jsonl + stats
    python prep_llm_review.py ocr [SHARDS]           # empty/failed docs still in review
    python prep_llm_review.py pos_mid [SHARDS]       # positives, 0.5 <= score < 0.9, no LLM verdict
    python prep_llm_review.py pilot [N]              # random N positives with score >= 0.9
    python prep_llm_review.py neg_recall [SHARDS]    # negatives, 0.3 <= score < 0.5 (optional)
"""
import json
import random
import sys
from collections import Counter

LLM_FIELDS = ("llm_is_match", "llm_spec", "llm_confidence", "llm_reason", "llm_model", "llm_reviewed")


def _read(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def load_base() -> dict:
    base = {r["url"]: r for r in _read("deep_run.jsonl")}
    for r in _read("llm_reviewed.jsonl"):
        b = base.get(r["url"])
        if b is not None:
            b.update({k: r[k] for k in LLM_FIELDS if k in r})
            b["decision"] = r["decision"]
            b["is_module_handbook"] = r["is_module_handbook"]
    return base


def write(name: str, recs: list, shards: int = 1) -> None:
    def dump(path, rows):
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({**r, "decision": "needs_review"}, ensure_ascii=False) + "\n")
        print(f"{path}: {len(rows)} docs")

    if shards <= 1:
        dump(f"{name}.jsonl", recs)
    else:
        for k in range(shards):
            dump(f"{name}.part{k}.jsonl", recs[k::shards])


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "base"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    base = load_base()
    recs = list(base.values())
    todo = [r for r in recs if not r.get("llm_reviewed")]
    sc = lambda r: r.get("module_handbook_score")  # noqa: E731
    pos = [r for r in todo if r["decision"] == "automatic_positive"]
    if mode == "base":
        with open("base.jsonl", "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("base.jsonl:", len(recs), dict(Counter(r["decision"] for r in recs)))
        print("llm verdicts carried over:", sum(bool(r.get("llm_reviewed")) for r in recs),
              dict(Counter(r["decision"] for r in recs if r.get("llm_reviewed"))))
        print("still unreviewed positives:", len(pos),
              "| >=0.9:", sum(sc(r) >= 0.9 for r in pos),
              "| 0.5-0.9:", sum(sc(r) < 0.9 for r in pos))
    elif mode == "ocr":
        write("review_ocr", [r for r in todo if r["decision"] == "needs_review"], arg or 1)
    elif mode == "pos_mid":
        write("review_pos_mid", [r for r in pos if sc(r) < 0.9], arg or 1)
    elif mode == "pilot":
        pool = [r for r in pos if sc(r) >= 0.9]
        random.seed(0)
        write("review_pilot", random.sample(pool, min(arg or 400, len(pool))))
    elif mode == "neg_recall":
        write("review_neg_recall",
              [r for r in todo if r["decision"] == "automatic_negative" and 0.3 <= (sc(r) or 0) < 0.5],
              arg or 1)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
