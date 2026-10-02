"""Cut the not-yet-reviewed rest of the suspect-host docs into fresh shards.

'Done' = URL present in any llm_suspect*.jsonl. Re-run safely after every interruption;
each call uses a new round number so no --out file is ever overwritten.

    python auswertung/resume_suspect.py [SHARDS]    # default 4
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(pattern):
    for f in sorted(glob.glob(str(ROOT / pattern))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


shards = int(sys.argv[1]) if len(sys.argv) > 1 else 4
universe = {}
for r in rows("review_suspect.part*.jsonl"):
    universe[r["url"]] = r
done = {r["url"] for r in rows("llm_suspect*.jsonl")}
todo = [r for u, r in universe.items() if u not in done]
print(f"universe {len(universe)}, done {len(universe) - len(todo)}, remaining {len(todo)}")
if not todo:
    sys.exit(0)
rounds = [int(m.group(1)) for p in glob.glob(str(ROOT / "review_suspect_r*_part*.jsonl"))
          if (m := re.search(r"_r(\d+)_part", p))]
rnd = max(rounds, default=1) + 1
bat = "webscraper-output-081757578883"
for k in range(shards):
    part = todo[k::shards]
    if not part:
        continue
    man = f"review_suspect_r{rnd}_part{k}.jsonl"
    with open(ROOT / man, "w", encoding="utf-8") as fh:
        for r in part:
            fh.write(json.dumps({**r, "decision": "needs_review"}, ensure_ascii=False) + "\n")
    print(rf".venv\Scripts\python -m mlclassifier.llm_review --manifest {man} --bucket {bat} "
          f"--out llm_suspect_r{rnd}_{k}.jsonl --workers 8 --no-verify-ssl")
