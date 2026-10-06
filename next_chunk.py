"""Cut the next small chunk of remaining work (for credentials that expire ~30 min).

    python next_chunk.py mid [PROCS] [CHUNK]    # LLM review of positives 0.5-0.9
    python next_chunk.py ocr [PROCS] [CHUNK]    # OCR of empty_document review-band docs

"Done" = URL already present in any earlier output file, so this can be re-run after
every interruption. Each call writes fresh manifests + fresh --out names (round
suffix), because the tools open --out with mode "w" and would overwrite old results.
"""
import glob
import json
import re
import sys

BUCKET = "webscraper-output-081757578883"
KINDS = {
    "mid": dict(src="review_pos_mid.part*.jsonl", out="llm_mid*.jsonl", prefix="llm_mid",
                keep=lambda r: True,
                cmd=".venv\\Scripts\\python -m mlclassifier.llm_review --manifest {m} "
                    "--bucket {b} --out {o} --workers 16"),
    "ocr": dict(src="review_ocr.part*.jsonl", out="ocr*.jsonl", prefix="ocr",
                keep=lambda r: r.get("extraction_status") == "empty_document",
                cmd=".venv\\Scripts\\python -m mlclassifier.reprocess_ocr --manifest {m} "
                    "--bucket {b} --out {o}"),
}


def rows(pattern):
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def main() -> None:
    kind = sys.argv[1]
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
    k = KINDS[kind]
    done = {r["url"] for r in rows(k["out"])}
    universe = [r for r in rows(k["src"]) if k["keep"](r)]
    todo = [r for r in universe if r["url"] not in done]
    print(f"{kind}: universe {len(universe)}, done {len(done & {r['url'] for r in universe})}, "
          f"remaining {len(todo)}")
    if not todo:
        return
    rounds = [int(m.group(1)) for p in glob.glob(f"{k['prefix']}_r*_*.jsonl")
              if (m := re.search(r"_r(\d+)_", p))]
    rnd = max(rounds, default=0) + 1
    batch = todo[: procs * chunk]
    print(f"round {rnd}: {len(batch)} docs in {procs} chunk(s) of <= {chunk}\n")
    for i in range(procs):
        part = batch[i::procs]
        if not part:
            continue
        man = f"chunk_{kind}_r{rnd}_{i}.jsonl"
        out = f"{k['prefix']}_r{rnd}_{i}.jsonl"
        with open(man, "w", encoding="utf-8") as fh:
            for r in part:
                fh.write(json.dumps({**r, "decision": "needs_review"}, ensure_ascii=False) + "\n")
        print(k["cmd"].format(m=man, b=BUCKET, o=out))


if __name__ == "__main__":
    main()
