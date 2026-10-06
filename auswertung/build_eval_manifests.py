"""Write eval_strict.jsonl / eval_likely.jsonl (decision = final yes/no) from final.jsonl.

strict = only LLM-confirmed;  likely = LLM-confirmed + never-reviewed TF-IDF >= 0.9.
"""
import json
from pathlib import Path

D = Path(__file__).resolve().parent / "data"
variants = {"strict": {"llm_confirmed"}, "likely": {"llm_confirmed", "tfidf_high"}}
outs = {v: open(D / f"eval_{v}.jsonl", "w", encoding="utf-8") for v in variants}
with open(D / "final.jsonl", encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        for v, pos in variants.items():
            dec = "automatic_positive" if r["tier"] in pos else ("needs_review" if r["tier"] == "unresolved" else "automatic_negative")
            outs[v].write(json.dumps({**r, "decision": dec, "is_module_handbook": dec == "automatic_positive",
                                      "llm_reviewed": True}, ensure_ascii=False) + "\n")
for f in outs.values():
    f.close()
