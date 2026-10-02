"""Shard the unreviewed TF-IDF>=0.9 docs on 'suspect' hosts for llm_review.

Suspect host = >=10 LLM-reviewed docs of the deep run and < 30% confirmed.
Writes review_suspect.partK.jsonl (decision set to needs_review so llm_review picks them up).

    python auswertung/prep_suspect.py [SHARDS]      # default 8
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
shards = int(sys.argv[1]) if len(sys.argv) > 1 else 8
docs = [json.loads(l) for l in open(ROOT / "auswertung/data/final.jsonl", encoding="utf-8")]
h = defaultdict(Counter)
for d in docs:
    if d["source_run"] == "deep_run" and d.get("llm_reviewed"):
        h[d["hostname"]]["rev"] += 1
        h[d["hostname"]]["conf"] += bool(d["llm_is_match"])
suspect = {k for k, v in h.items() if v["rev"] >= 10 and v["conf"] / v["rev"] < 0.3}
todo = [d for d in docs if d["tier"] == "tfidf_high" and d["hostname"] in suspect]
todo.sort(key=lambda d: d["hostname"])  # interleave below so every shard mixes hosts
print(f"{len(suspect)} suspect hosts, {len(todo)} docs")
for k in range(shards):
    part = todo[k::shards]
    with open(ROOT / f"review_suspect.part{k}.jsonl", "w", encoding="utf-8") as fh:
        for d in part:
            fh.write(json.dumps({**d, "decision": "needs_review"}, ensure_ascii=False) + "\n")
    print(f"review_suspect.part{k}.jsonl: {len(part)}")
