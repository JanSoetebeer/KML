"""All charts + key figures for the project report. Run after build_final.py and the
two evaluation runs (eval_strict / eval_likely).

    .venv\\Scripts\\python auswertung\\make_charts.py

Writes PNGs to auswertung/charts/ and auswertung/data/kennzahlen.json.
"""
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "auswertung" / "data"
OUT = ROOT / "auswertung" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

# --- palette (validated reference palette, light mode) + fixed entity colours -------------
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
GRAY = "#9a9a96"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2dd"
TIER_COL = {"llm_confirmed": BLUE, "tfidf_high": AQUA, "llm_rejected": ORANGE,
            "tfidf_negative": GRAY, "unresolved": YELLOW, "tfidf_other": MAGENTA, "llm_lowconf": VIOLET}
TIER_LABEL = {"llm_confirmed": "LLM bestätigt", "tfidf_high": "TF-IDF ≥ 0,9 (nicht LLM-geprüft)",
              "llm_rejected": "LLM verworfen", "tfidf_negative": "TF-IDF negativ (nicht LLM-geprüft)",
              "unresolved": "ungeklärt (kein Text/Fehler)", "tfidf_other": "Positiv aus anderem Lauf (ungeprüft)",
              "llm_lowconf": "LLM unsicher"}

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "text.color": INK,
})

KEY: dict = {}


def fmt(n):
    return f"{n:,.0f}".replace(",", ".")


def save(fig, name, note=None):
    for a in fig.axes:
        for axis, lim, sc in ((a.xaxis, a.get_xlim(), a.get_xscale()), (a.yaxis, a.get_ylim(), a.get_yscale())):
            if (sc == "linear" and max(abs(lim[0]), abs(lim[1])) >= 10000
                    and isinstance(axis.get_major_formatter(), matplotlib.ticker.ScalarFormatter)):
                axis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt(v)))
    if note:
        import textwrap

        note = chr(10).join(textwrap.wrap(note, 120))
        fig.text(0.01, -0.03, note, fontsize=7.5, color=INK2, ha="left", va="top")
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("chart", name)


def wilson(k, n, z=1.96):
    if n == 0:
        return 0, 0, 0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def bar_labels(ax, bars, fmtf=fmt, pad=3, horizontal=False):
    for b in bars:
        if horizontal:
            ax.text(b.get_width() + pad, b.get_y() + b.get_height() / 2, fmtf(b.get_width()),
                    va="center", fontsize=8.5, color=INK2)
        else:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + pad, fmtf(b.get_height()),
                    ha="center", va="bottom", fontsize=8.5, color=INK2)


# ------------------------------------------------------------------------------------------
docs = [json.loads(l) for l in open(DATA / "final.jsonl", encoding="utf-8")]
N = len(docs)
tiers = Counter(d["tier"] for d in docs)
by_src = defaultdict(Counter)
for d in docs:
    by_src[d["source_run"]][d["tier"]] += 1
deep = [d for d in docs if d["source_run"] == "deep_run"]
reviewed = [d for d in docs if d.get("llm_reviewed")]
KEY["docs_total"] = N
KEY["tiers"] = dict(tiers)
KEY["by_source"] = {k: dict(v) for k, v in by_src.items()}
KEY["llm_reviewed_docs"] = len(reviewed)

# pilot-based precision of the never-reviewed high-score group
pilot = [d for d in deep if d.get("llm_batch") == "llm_pilot.jsonl"]
pk = sum(1 for d in pilot if d["llm_is_match"])
p, lo, hi = wilson(pk, len(pilot))
KEY["pilot"] = {"n": len(pilot), "confirmed": pk, "precision": p, "ci95": [lo, hi]}
n_high = tiers["tfidf_high"]
KEY["estimate_true_in_tfidf_high"] = {"mid": round(n_high * p), "low": round(n_high * lo), "high": round(n_high * hi)}
conf = tiers["llm_confirmed"]
KEY["final_strict"] = conf
KEY["final_likely_estimated_true"] = {
    "mid": conf + round(n_high * p), "low": conf + round(n_high * lo), "high": conf + round(n_high * hi)}
KEY["final_likely_listed"] = conf + n_high

# 01 -- funnel ---------------------------------------------------------------------------
init_pos = sum(1 for d in docs if d["decision"] == "automatic_positive")
KEY["initial_tfidf_positive"] = init_pos
stages = [
    ("Heruntergeladene PDFs (alle Läufe, URL-eindeutig)", N, GRAY),
    ("Vom TF-IDF-Klassifikator als positiv eingestuft", init_pos, AQUA),
    ("Davon LLM-geprüft + bestätigt", conf, BLUE),
    ("Nach LLM: Geschätzt echte Modulhandbücher (inkl. ungeprüfte ≥ 0,9)", KEY["final_likely_estimated_true"]["mid"], BLUE),
]
fig, ax = plt.subplots(figsize=(9, 3.6))
bars = ax.barh([s[0] for s in stages][::-1], [s[1] for s in stages][::-1], color=[s[2] for s in stages][::-1], height=0.55)
bar_labels(ax, bars, horizontal=True, pad=1200)
ax.set_xlim(0, N * 1.12)
ax.set_title("Vom Crawl zum Modulhandbuch: Trichter über alle Läufe")
ax.grid(axis="y", visible=False)
ax.set_xlabel("Dokumente")
save(fig, "01_trichter")

# 02 -- tier composition per source --------------------------------------------------------
order = ["llm_confirmed", "tfidf_high", "tfidf_other", "llm_rejected", "tfidf_negative", "unresolved"]
srcs = [("deep_run", "Deep Run (Sep)"), ("run_full_aug", "Lauf August (nur dort gefunden)")]
fig, ax = plt.subplots(figsize=(9.5, 2.9))
left = np.zeros(len(srcs))
for t in order:
    vals = np.array([by_src[s][t] for s, _ in srcs], dtype=float)
    ax.barh([l for _, l in srcs][::-1], vals[::-1], left=left[::-1], color=TIER_COL[t], label=TIER_LABEL[t],
            height=0.55, edgecolor="white", linewidth=1.2)
    left += vals
ax.set_title("Endstatus aller Dokumente nach Quelle")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, fontsize=8)
ax.set_xlabel("Dokumente")
ax.grid(axis="y", visible=False)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt(v)))
save(fig, "02_endstatus_nach_quelle")

# 03 -- TF-IDF precision by score bin (LLM as reference) -----------------------------------
bins = [(0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)]


def pick(lo_, hi_):
    """Unbiased source per band: all unreviewed positives 0.5-0.9 (mid pass), the random
    pilot for >= 0.9, the old review-band sample (biased, hard cases) for 0.3-0.5."""
    if lo_ >= 0.9:
        key = "llm_pilot"
    elif lo_ >= 0.5:
        key = "llm_mid"
    else:
        key = "llm_reviewed"
    return [d for d in deep if d.get("llm_batch", "").startswith(key) and d.get("module_handbook_score") is not None
            and lo_ <= d["module_handbook_score"] < hi_]


rows3 = []
for lo_, hi_ in bins:
    sel = pick(lo_, hi_)
    k = sum(1 for d in sel if d["llm_is_match"])
    pp, a, b = wilson(k, len(sel))
    rows3.append((f"{lo_:.1f}–{min(hi_, 1.0):.1f}".replace(".", ","), len(sel), pp, a, b))
KEY["precision_by_score_bin"] = [dict(bin=r[0], n=r[1], confirm_rate=r[2], ci_lo=r[3], ci_hi=r[4]) for r in rows3]
fig, ax = plt.subplots(figsize=(9, 4.4))
xs = np.arange(len(rows3))
vals = np.array([r[2] for r in rows3]) * 100
err = np.array([[r[2] - r[3] for r in rows3], [r[4] - r[2] for r in rows3]]) * 100
bars = ax.bar(xs, vals, color=[GRAY, GRAY] + [BLUE] * 5, width=0.6)
ax.errorbar(xs, vals, yerr=err, fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
for x, r in zip(xs, rows3):
    ax.text(x, r[4] * 100 + 2.5, f"{r[2]*100:.0f} %\nn={fmt(r[1])}", ha="center", fontsize=8.5, color=INK2)
ax.axhline(96.5, color=ORANGE, lw=1.2, ls="--")
ax.text(len(rows3) - 0.5, 98, "Precision im Training (Cross-Validation): 96,5 %", color=ORANGE, fontsize=8.5, ha="right", va="bottom")
ax.set_xticks(xs, [r[0] for r in rows3])
ax.set_ylim(0, 112)
ax.set_xlabel("TF-IDF-Score des Dokuments")
ax.set_ylabel("Vom LLM als Modulhandbuch bestätigt (%)")
ax.set_title("Wie verlässlich ist der TF-IDF-Score? LLM-Bestätigungsrate je Score-Bereich")
ax.grid(axis="x", visible=False)
save(fig, "03_precision_je_score", "Referenz = Claude Haiku 4.5 (Bedrock), Fehlerbalken = 95-%-Wilson-Intervall. 0,5–0,9: alle bis dahin ungeprüften Positiven; ≥ 0,9: zufälliger Pilot (n=400); grau 0,3–0,5: kleine Stichprobe schwieriger Fälle aus dem alten Review-Band (nicht repräsentativ).")

# 04 -- score histogram by tier -------------------------------------------------------------
edges = np.arange(0, 1.0001, 0.05)
fig, ax = plt.subplots(figsize=(9.5, 4.4))
bottom = np.zeros(len(edges) - 1)
for t in ["tfidf_negative", "llm_rejected", "llm_confirmed", "tfidf_high"]:
    sc = [d["module_handbook_score"] for d in deep if d["tier"] == t and d.get("module_handbook_score") is not None]
    h, _ = np.histogram(sc, bins=edges)
    ax.bar(edges[:-1] + 0.025, h, width=0.045, bottom=bottom, color=TIER_COL[t], label=TIER_LABEL[t])
    bottom += h
ax.set_yscale("log")
ax.set_xlabel("TF-IDF-Score")
ax.set_ylabel("Dokumente (log)")
ax.set_title("Score-Verteilung des Deep Runs, eingefärbt nach Endstatus")
ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
ax.grid(axis="x", visible=False)
save(fig, "04_score_histogramm")

# 05 -- LLM runs ----------------------------------------------------------------------------
batches = [("llm_reviewed.jsonl", "Review-Band Aug-Lauf\n(Score 0,3–0,7)"), ("llm_mid", "Positive 0,5–0,9\n(Deep Run)"),
           ("llm_pilot.jsonl", "Stichprobe Positive ≥ 0,9"), ("llm_ocr.jsonl", "OCR-Treffer\n(Score ≥ 0,5)")]
fig, ax = plt.subplots(figsize=(9, 4.2))
b_c, b_r = [], []
for key, _ in batches:
    sel = [d for d in reviewed if d.get("llm_batch", "").startswith(key.replace(".jsonl", ""))]
    b_c.append(sum(1 for d in sel if d["llm_is_match"]))
    b_r.append(sum(1 for d in sel if not d["llm_is_match"]))
x = np.arange(len(batches))
ax.bar(x, b_c, color=BLUE, width=0.55, label="bestätigt", edgecolor="white", linewidth=1.2)
ax.bar(x, b_r, bottom=b_c, color=ORANGE, width=0.55, label="verworfen", edgecolor="white", linewidth=1.2)
for xi, c, r in zip(x, b_c, b_r):
    ax.text(xi, c + r + 300, f"{fmt(c+r)} geprüft\n{c/(c+r)*100:.0f} % bestätigt", ha="center", fontsize=8.5, color=INK2)
ax.set_xticks(x, [b[1] for b in batches], fontsize=8.5)
ax.set_ylabel("Dokumente")
ax.set_title("LLM-Review: Umfang und Ergebnis je Lauf")
ax.legend()
ax.set_ylim(0, max(np.array(b_c) + np.array(b_r)) * 1.18)
ax.grid(axis="x", visible=False)
KEY["llm_batches"] = {b[0]: {"confirmed": c, "rejected": r} for b, c, r in zip(batches, b_c, b_r)}
save(fig, "05_llm_laeufe")

# 06 -- confidence -------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 3.8))
cb = np.round(np.array([d.get("llm_confidence") or 0 for d in reviewed]), 1)
for i, (flag, col, lab) in enumerate([(True, BLUE, "bestätigt"), (False, ORANGE, "verworfen")]):
    vals_ = [v for v, d in zip(cb, reviewed) if bool(d["llm_is_match"]) == flag]
    cnt = Counter(vals_)
    xs_ = sorted(cnt)
    ax.bar(np.array(xs_) + (i - 0.5) * 0.04, [cnt[v] for v in xs_], width=0.04, color=col, label=lab)
ax.set_yscale("log")
ax.set_xlabel("Vom Modell angegebene Konfidenz")
ax.set_ylabel("Dokumente (log)")
ax.set_title("Konfidenz der LLM-Urteile")
ax.legend()
save(fig, "06_llm_konfidenz")

# 07 -- error types of the classifier -----------------------------------------------------
CATS = [
    ("Prüfungs-/Studienordnung, Satzung", r"pr.fungsordnung|studienordnung|\bspo\b|regulation|satzung|ordnung|bestimmungen"),
    ("Einzelnes Modul / Datenblatt / Syllabus", r"single (module|course)|one module|einzel|datasheet|data sheet|syllabus|single document"),
    ("Studienverlaufs-/Studienplan", r"verlaufsplan|study (plan|schedule|progression)|studienplan|schedule|plan only"),
    ("Vorlesungs-/Veranstaltungsverzeichnis", r"vorlesungsverzeichnis|timetable|lecture (schedule|directory|list)|stundenplan|veranstaltungsverzeichnis|course (catalog|listing|directory)"),
    ("Modul-/Wahlpflichtkatalog (unvollständig)", r"catalog|katalog|elective|overview|übersicht"),
    ("Antrag, Formular, Merkblatt, Flyer", r"antrag|formular|application|flyer|brochure|leaflet|merkblatt|faq|guide|form\b|brosch"),
]


def cat_of(reason):
    r = (reason or "").lower()
    for name, rx in CATS:
        if re.search(rx, r):
            return name
    return "Sonstiges"


fp = [d for d in docs if d["tier"] == "llm_rejected" and d["decision"] == "automatic_positive"]
cc = Counter(cat_of(d["llm_reason"]) for d in fp)
KEY["false_positive_types"] = dict(cc)
KEY["n_false_positives_by_llm"] = len(fp)
items = sorted(cc.items(), key=lambda kv: kv[1])
fig, ax = plt.subplots(figsize=(9, 4))
bars = ax.barh([i[0] for i in items], [i[1] for i in items], color=ORANGE, height=0.55)
bar_labels(ax, bars, horizontal=True, pad=60)
ax.set_xlim(0, max(i[1] for i in items) * 1.15)
ax.set_title(f"Was der Klassifikator fälschlich als Modulhandbuch hielt (n = {fmt(len(fp))})")
ax.set_xlabel("Dokumente (vom LLM verworfene TF-IDF-Positive)")
ax.grid(axis="y", visible=False)
save(fig, "07_fehlerarten", "Kategorien per Stichwortzuordnung aus der LLM-Begründung; „Sonstiges“ = nicht zuordenbar.")

# 08 -- filename heuristic ------------------------------------------------------------------
KW = re.compile(r"modul|mhb|handbuch|handbook|module|mh[_-]", re.I)
bands = [("0,5–0,7", 0.5, 0.7), ("0,7–0,9", 0.7, 0.9), ("≥ 0,9", 0.9, 1.01)]
fig, ax = plt.subplots(figsize=(8.5, 4))
w = 0.34
res = {}
for j, (flag, col, lab) in enumerate([(True, BLUE, "Dateiname enthält „modul/handbuch/mhb“"), (False, GRAY, "ohne Stichwort im Dateinamen")]):
    rates, ns = [], []
    for _, lo_, hi_ in bands:
        sel = [d for d in deep if d.get("llm_reviewed") and d.get("module_handbook_score") is not None
               and lo_ <= d["module_handbook_score"] < hi_ and bool(KW.search(d["filename"])) == flag]
        k = sum(1 for d in sel if d["llm_is_match"])
        rates.append(k / len(sel) * 100 if sel else 0)
        ns.append(len(sel))
    res[lab] = list(zip(rates, ns))
    bb = ax.bar(np.arange(len(bands)) + (j - 0.5) * w, rates, width=w, color=col, label=lab)
    for b, r_, n_ in zip(bb, rates, ns):
        ax.text(b.get_x() + b.get_width() / 2, r_ + 1.5, f"{r_:.0f} %\nn={fmt(n_)}", ha="center", fontsize=8, color=INK2)
ax.set_xticks(np.arange(len(bands)), [b[0] for b in bands])
ax.set_ylim(0, 115)
ax.set_xlabel("TF-IDF-Score")
ax.set_ylabel("Vom LLM bestätigt (%)")
ax.set_title("Der Dateiname ist ein starkes Zusatzsignal")
ax.legend(fontsize=8, loc="upper left")
ax.grid(axis="x", visible=False)
KEY["filename_keyword_effect"] = {k: [dict(rate=r, n=n) for r, n in v] for k, v in res.items()}
save(fig, "08_dateiname_signal")

# 09 -- OCR funnel --------------------------------------------------------------------------
ocr_docs = [d for d in docs if d.get("ocr_reprocessed")]
ocr_text = [d for d in ocr_docs if d["extraction_status"] != "empty_document"]
ocr_hi = [d for d in ocr_docs if (d.get("module_handbook_score") or 0) >= 0.5]
ocr_conf = [d for d in ocr_hi if d["tier"] == "llm_confirmed"]
fun = [("Gescannte PDFs ohne Textebene (Review-Band)", 3619, GRAY), ("OCR durchgeführt", len(ocr_docs), GRAY),
       ("Text per OCR gewonnen", len(ocr_text), AQUA), ("Score ≥ 0,5 → an LLM", len(ocr_hi), AQUA),
       ("LLM bestätigt", len(ocr_conf), BLUE)]
KEY["ocr"] = {s[0]: s[1] for s in fun}
fig, ax = plt.subplots(figsize=(8.5, 3.6))
bars = ax.barh([f[0] for f in fun][::-1], [f[1] for f in fun][::-1], color=[f[2] for f in fun][::-1], height=0.55)
bar_labels(ax, bars, horizontal=True, pad=40)
ax.set_xlim(0, 4300)
ax.set_title("OCR-Nachbearbeitung: viel Aufwand, wenig Ertrag")
ax.grid(axis="y", visible=False)
save(fig, "09_ocr_trichter")

# 10 -- uni-level charts ---------------------------------------------------------------------
ps = {r["csv_id"]: r for r in json.load(open(DATA / "per_uni_strict.json", encoding="utf-8"))}
pl = {r["csv_id"]: r for r in json.load(open(DATA / "per_uni_likely.json", encoding="utf-8"))}
cids = list(pl)
B = [(0, 0, "0"), (1, 1, "1"), (2, 4, "2–4"), (5, 9, "5–9"), (10, 24, "10–24"), (25, 49, "25–49"), (50, 99, "50–99"), (100, 249, "100–249"), (250, 10**9, "≥ 250")]


def hist_unis(src):
    return [sum(1 for c in cids if lo_ <= src[c]["mh_positive"] <= hi_) for lo_, hi_, _ in B]


hs, hl = hist_unis(ps), hist_unis(pl)
fig, ax = plt.subplots(figsize=(9.5, 4.2))
x = np.arange(len(B))
ax.bar(x - 0.2, hs, width=0.4, color=BLUE, label="nur LLM-bestätigt")
ax.bar(x + 0.2, hl, width=0.4, color=AQUA, label="inkl. TF-IDF ≥ 0,9 (ungeprüft)")
for xi, a, b in zip(x, hs, hl):
    ax.text(xi - 0.2, a + 2, str(a), ha="center", fontsize=8, color=INK2)
    ax.text(xi + 0.2, b + 2, str(b), ha="center", fontsize=8, color=INK2)
ax.set_xticks(x, [b[2] for b in B])
ax.set_xlabel("Modulhandbücher pro Hochschule")
ax.set_ylabel(f"Hochschulen (von {len(cids)})")
ax.set_title("Verteilung: Wie viele Modulhandbücher pro Hochschule?")
ax.legend()
ax.grid(axis="x", visible=False)
KEY["unis_total"] = len(cids)
KEY["unis_with_mh_strict"] = sum(1 for c in cids if ps[c]["mh_positive"] > 0)
KEY["unis_with_mh_likely"] = sum(1 for c in cids if pl[c]["mh_positive"] > 0)
KEY["unis_with_ge10_likely"] = sum(1 for c in cids if pl[c]["mh_positive"] >= 10)
KEY["unis_with_ge10_strict"] = sum(1 for c in cids if ps[c]["mh_positive"] >= 10)
vals_l = sorted(pl[c]["mh_positive"] for c in cids)
KEY["mh_per_uni_median_likely"] = float(np.median(vals_l))
top10 = sum(sorted(vals_l)[-10:])
KEY["top10_unis_share_likely"] = top10 / max(1, sum(vals_l))
save(fig, "10_mh_pro_hochschule")

# 11 -- coverage by segment ------------------------------------------------------------------
es = json.load(open(DATA / "eval_strict.json", encoding="utf-8"))
el = json.load(open(DATA / "eval_likely.json", encoding="utf-8"))


def seg(e, prefix):
    return {s["key"].split(":", 1)[1]: s["metrics"] for s in e["scenarios"] if s["key"].startswith(prefix)}


def seg_chart(prefix, title, fname, order=None, figh=3.6):
    a, b = seg(es, prefix), seg(el, prefix)
    keys = [k for k in (order or sorted(b, key=lambda k: -b[k]["n_unis"])) if k in b and b[k]["n_unis"] > 0]
    fig, ax = plt.subplots(figsize=(9, figh))
    y = np.arange(len(keys))
    ca = [a[k]["n_unis_with_coverage"] / a[k]["n_unis"] * 100 for k in keys]
    cb_ = [b[k]["n_unis_with_coverage"] / b[k]["n_unis"] * 100 for k in keys]
    ax.barh(y + 0.2, ca, height=0.38, color=BLUE, label="nur LLM-bestätigt")
    ax.barh(y - 0.2, cb_, height=0.38, color=AQUA, label="inkl. TF-IDF ≥ 0,9")
    for yi, k, va, vb in zip(y, keys, ca, cb_):
        ax.text(vb + 1, yi - 0.2, f"{vb:.0f} %  ({b[k]['n_unis_with_coverage']}/{b[k]['n_unis']}) · {fmt(b[k]['mh_positive'])} MH", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, keys)
    ax.invert_yaxis()
    ax.set_xlim(0, 135)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("Hochschulen mit ≥ 1 Modulhandbuch (%)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", visible=False)
    save(fig, fname)
    return {k: dict(n=b[k]["n_unis"], with_mh=b[k]["n_unis_with_coverage"], mh=b[k]["mh_positive"]) for k in keys}


KEY["seg_type"] = seg_chart("type:", "Abdeckung nach Hochschultyp", "11_abdeckung_typ")
KEY["seg_traeger"] = seg_chart("traeger:", "Abdeckung nach Trägerschaft", "12_abdeckung_traeger", figh=2.8)
KEY["seg_size"] = seg_chart("size:", "Abdeckung nach Größe (Studierende)", "13_abdeckung_groesse",
                            order=["<1.000", "1.000–5.000", "5.000–15.000", "15.000–30.000", ">30.000"], figh=3.4)
KEY["seg_land"] = seg_chart("land:", "Abdeckung nach Bundesland", "14_abdeckung_bundesland", figh=6)

# 15 -- uni flags before/after ---------------------------------------------------------------
old = {r["csv_id"]: r for r in json.load(open(ROOT / "per_uni.json", encoding="utf-8"))}
FL = [("ok", "ok (≥ 3 MH)", BLUE), ("low_recall", "wenige MH (< 3)", AQUA), ("no_positive", "Dokumente, aber kein MH", ORANGE), ("no_docs_no_seeds", "nichts gefunden", GRAY)]
fig, ax = plt.subplots(figsize=(9, 3.2))
cases = [("Vor der Bereinigung\n(TF-IDF-Positive)", Counter(r["flag"] for r in old.values())),
         ("Nach der Bereinigung\ninkl. ≥ 0,9 ungeprüft", Counter(r["flag"] for r in pl.values())),
         ("Nach der Bereinigung\nnur LLM-bestätigt", Counter(r["flag"] for r in ps.values()))]
left = np.zeros(len(cases))
for fkey, flab, col in FL:
    v = np.array([c[1][fkey] for c in cases], dtype=float)
    ax.barh([c[0] for c in cases][::-1], v[::-1], left=left[::-1], color=col, label=flab, height=0.55, edgecolor="white", linewidth=1.2)
    for yi, (vi, li) in enumerate(zip(v[::-1], left[::-1])):
        if vi > 12:
            ax.text(li + vi / 2, yi, int(vi), ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
    left += v
ax.set_title("Hochschul-Status: wie viele Hochschulen sind gut abgedeckt?")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4, fontsize=8)
ax.grid(axis="y", visible=False)
ax.set_xlabel("Hochschulen")
KEY["flags"] = {c[0].replace("\n", " "): dict(c[1]) for c in cases}
save(fig, "15_hochschul_status")

# 16 -- scatter size vs MH --------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.5, 5.2))
tcol = {"Universität": BLUE, "Fachhochschule / HAW": ORANGE, "Künstlerische Hochschule": AQUA}
used = set()
for c in cids:
    r = pl[c]
    try:
        st = float(r["students"])
    except (TypeError, ValueError):
        continue
    if st <= 0:
        continue
    t = r["uni_type"]
    col = tcol.get(t, GRAY)
    lab = t if (t in tcol and t not in used) else ("Sonstige" if t not in tcol and "Sonstige" not in used else None)
    used.add(t if t in tcol else "Sonstige")
    ax.scatter(st, r["mh_positive"] + 0.8, s=22, color=col, alpha=0.75, edgecolor="white", linewidth=0.5, label=lab)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Studierende (log)")
ax.set_ylabel("Modulhandbücher + 1 (log)")
ax.set_title("Größe erklärt die Ausbeute nur teilweise")
ax.legend(fontsize=8)
save(fig, "16_groesse_vs_ausbeute", "Pro Punkt eine Hochschule; Hochschultypen siehe Legende. „+1“ erlaubt die Darstellung von Hochschulen ohne Treffer.")

# 17 -- top hosts ----------------------------------------------------------------------------
hc = defaultdict(Counter)
for d in docs:
    if d["tier"] in ("llm_confirmed", "tfidf_high"):
        hc[d["hostname"]][d["tier"]] += 1
top = sorted(hc, key=lambda h: -sum(hc[h].values()))[:20]
fig, ax = plt.subplots(figsize=(9, 5.6))
y = np.arange(len(top))
a_ = [hc[h]["llm_confirmed"] for h in top]
b_ = [hc[h]["tfidf_high"] for h in top]
ax.barh(y, a_, color=BLUE, label=TIER_LABEL["llm_confirmed"], height=0.6, edgecolor="white", linewidth=1)
ax.barh(y, b_, left=a_, color=AQUA, label=TIER_LABEL["tfidf_high"], height=0.6, edgecolor="white", linewidth=1)
ax.set_yticks(y, top, fontsize=8.5)
ax.invert_yaxis()
ax.set_title("Die 20 ergiebigsten Hosts")
ax.set_xlabel("Modulhandbücher")
ax.legend(fontsize=8, loc="lower right")
ax.grid(axis="y", visible=False)
KEY["top_hosts"] = {h: sum(hc[h].values()) for h in top}
save(fig, "17_top_hosts")

# 18 -- time: docs/h per run -------------------------------------------------------------------
def hour(d):
    return datetime.fromisoformat(d["crawled_at"]).replace(minute=0, second=0, microsecond=0)


def raw(p):
    return [json.loads(l) for l in open(ROOT / p, encoding="utf-8") if l.strip()]


runs_t = {"Aug-Lauf (12.08.)": raw("run_full.jsonl"), "Deep Run (16.–17.09.)": raw("deep_run.jsonl")}
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
KEY["throughput"] = {}
for ax, (name, rs) in zip(axes, runs_t.items()):
    hc_ = Counter(hour(d) for d in rs)
    xs_ = sorted(hc_)
    ax.bar(range(len(xs_)), [hc_[x_] for x_ in xs_], color=BLUE, width=0.8)
    ax.set_xticks(range(0, len(xs_), max(1, len(xs_) // 6)), [xs_[i].strftime("%d.%m. %Hh") for i in range(0, len(xs_), max(1, len(xs_) // 6))], fontsize=7.5, rotation=30)
    ax.set_title(name, fontsize=10.5)
    ax.grid(axis="x", visible=False)
    KEY["throughput"][name] = dict(hours=len(xs_), docs=len(rs), peak_docs_per_hour=max(hc_.values()))
axes[0].set_ylabel("neue PDFs pro Stunde")
fig.suptitle("Crawl-Durchsatz", x=0.01, ha="left", fontweight="bold", fontsize=12)
save(fig, "18_durchsatz")

# 19 -- years in filenames ----------------------------------------------------------------------
yh_s = es["temporal"]["year_hist"]
yh_l = el["temporal"]["year_hist"]
yrs = list(range(2010, 2028))
fig, ax = plt.subplots(figsize=(9.5, 3.8))
ax.bar(np.array(yrs) - 0.2, [yh_s.get(str(y_), 0) for y_ in yrs], width=0.4, color=BLUE, label="nur LLM-bestätigt")
ax.bar(np.array(yrs) + 0.2, [yh_l.get(str(y_), 0) for y_ in yrs], width=0.4, color=AQUA, label="inkl. TF-IDF ≥ 0,9")
ax.set_xticks(yrs, [str(y_) for y_ in yrs], fontsize=8, rotation=45)
ax.set_title("Aktualität: Jahreszahl im Dateinamen der Modulhandbücher")
ax.set_ylabel("Dokumente")
ax.legend(fontsize=8)
ax.grid(axis="x", visible=False)
KEY["year_in_filename"] = {"strict_with_year": es["temporal"]["n_with_year"], "strict_without": es["temporal"]["n_without_year"],
                           "likely_with_year": el["temporal"]["n_with_year"], "likely_without": el["temporal"]["n_without_year"]}
save(fig, "19_jahre_im_dateinamen", "Nur Dokumente, deren Dateiname eine Jahreszahl enthält; ohne Jahr: " + fmt(es["temporal"]["n_without_year"]) + " (streng).")

# 20 -- runs comparison + URL overlap --------------------------------------------------------------
rf_raw, dp_raw = raw("run_full.jsonl"), raw("deep_run.jsonl")
ru, du = {r["url"] for r in rf_raw}, {r["url"] for r in dp_raw}
rh, dh = {r["hostname"] for r in rf_raw}, {r["hostname"] for r in dp_raw}
KEY["runs"] = {"aug_urls": len(ru), "deep_urls": len(du), "overlap_urls": len(ru & du), "aug_hosts": len(rh), "deep_hosts": len(dh),
               "hosts_only_aug": len(rh - dh), "hosts_only_deep": len(dh - rh),
               "aug_raw_pos": sum(r["decision"] == "automatic_positive" for r in rf_raw),
               "deep_raw_pos": sum(r["decision"] == "automatic_positive" for r in dp_raw)}
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
ax = axes[0]
parts = [("nur Aug-Lauf", len(ru - du), MAGENTA), ("beide", len(ru & du), GRAY), ("nur Deep Run", len(du - ru), BLUE)]
left = 0
for i_, (lab, v, col) in enumerate(parts):
    ax.barh([0], [v], left=left, color=col, height=0.5, edgecolor="white", linewidth=1.2)
    ax.text(left + v / 2, 0.32 + 0.30 * (i_ % 2), f"{lab}: {fmt(v)}", ha="center", va="bottom", color=INK, fontsize=8.5, fontweight="bold")
    left += v
ax.set_ylim(-0.4, 1.1)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
ax.set_yticks([])
ax.set_title("URL-Überlappung der Läufe")
ax.grid(visible=False)
ax = axes[1]
ax.bar([0, 1, 2.4, 3.4], [len(rh - dh), len(rh & dh), len(dh - rh), 0], color=[MAGENTA, GRAY, BLUE, "white"], width=0.7)
ax.cla()
labs = ["nur Aug", "beide", "nur Deep"]
vals_h = [len(rh - dh), len(rh & dh), len(dh - rh)]
bars = ax.bar(labs, vals_h, color=[MAGENTA, GRAY, BLUE], width=0.6)
bar_labels(ax, bars, pad=8)
ax.set_title("Hosts (Domains) je Lauf")
ax.set_ylim(0, max(vals_h) * 1.15)
ax.grid(axis="x", visible=False)
save(fig, "20_laeufe_vergleich")

# 21 -- recall gap: estimated missed in 0.3-0.5 --------------------------------------------------
neg_band = [d for d in deep if d["tier"] == "tfidf_negative" and d.get("module_handbook_score") is not None
            and 0.3 <= d["module_handbook_score"] < 0.5]
cr = {r["bin"]: r["confirm_rate"] for r in KEY["precision_by_score_bin"]}
est_missed = sum(1 for d in neg_band if 0.3 <= d["module_handbook_score"] < 0.4) * cr.get("0,3–0,4", 0) + \
    sum(1 for d in neg_band if 0.4 <= d["module_handbook_score"] < 0.5) * cr.get("0,4–0,5", 0)
KEY["recall_gap"] = {"neg_docs_0.3_0.5_unreviewed": len(neg_band), "estimated_missed_mh": round(est_missed)}
fig, ax = plt.subplots(figsize=(8, 3.8))
cats_ = ["Bestätigt (LLM)", "Geschätzt echt in\nTF-IDF ≥ 0,9", "Möglicherweise verpasst\n(Negative 0,3–0,5)"]
vals_ = [conf, KEY["estimate_true_in_tfidf_high"]["mid"], round(est_missed)]
bars = ax.bar(cats_, vals_, color=[BLUE, AQUA, ORANGE], width=0.55)
bar_labels(ax, bars, pad=150)
ax.set_ylim(0, max(vals_) * 1.15)
ax.set_title("Precision vs. Recall: was wir haben und was fehlen könnte (grobe Schätzung)")
ax.set_ylabel("Dokumente")
ax.grid(axis="x", visible=False)
save(fig, "21_recall_luecke", "Schätzung aus den Bestätigungsraten je Score-Bereich (Abb. 03); der Wert für Negative 0,3–0,5 beruht auf einer kleinen, nicht repräsentativen Stichprobe und ist sehr unsicher.")

# 22 -- dedup -------------------------------------------------------------------------------------
keep = [d for d in docs if d["tier"] in ("llm_confirmed", "tfidf_high")]
uniq = len({(d["hostname"], d["filename"]) for d in keep})
uniq_s = len({(d["hostname"], d["filename"]) for d in docs if d["tier"] == "llm_confirmed"})
KEY["dedup"] = {"likely_docs": len(keep), "likely_unique_host_filename": uniq, "strict_docs": conf, "strict_unique_host_filename": uniq_s}
fig, ax = plt.subplots(figsize=(7.5, 3.2))
x = np.arange(2)
ax.bar(x - 0.2, [conf, len(keep)], width=0.4, color=GRAY, label="Dokumente (URLs)")
ax.bar(x + 0.2, [uniq_s, uniq], width=0.4, color=BLUE, label="nach Entfernen von Duplikaten (Host + Dateiname)")
for xi, a, b in zip(x, [conf, len(keep)], [uniq_s, uniq]):
    ax.text(xi - 0.2, a + 150, fmt(a), ha="center", fontsize=8.5, color=INK2)
    ax.text(xi + 0.2, b + 150, fmt(b), ha="center", fontsize=8.5, color=INK2)
ax.set_xticks(x, ["nur LLM-bestätigt", "inkl. TF-IDF ≥ 0,9"])
ax.set_ylim(0, len(keep) * 1.18)
ax.set_title("Duplikate in der Endliste")
ax.legend(fontsize=8, loc="upper left")
ax.grid(axis="x", visible=False)
save(fig, "22_duplikate")

# 23 -- training metrics vs reality ------------------------------------------------------------
tr = json.load(open(ROOT / "mlclassifier/artifacts/training_report.json", encoding="utf-8"))
c = tr["variants"]["content"]
fig, ax = plt.subplots(figsize=(8, 3.8))
m = ["Precision", "Recall"]
tr_vals = [c["at_recall_target"]["precision"] * 100, c["at_recall_target"]["recall"] * 100]
ax.bar(np.arange(2) - 0.2, tr_vals, width=0.4, color=GRAY, label=f"Training (CV, {fmt(tr['n_docs'])} Dokumente, {tr['n_universities']} Hochschulen)")
real_p = KEY["pilot"]["precision"] * 100
mid_rate = [r for r in KEY["precision_by_score_bin"] if r["bin"] in ("0,5–0,6", "0,6–0,7", "0,7–0,8", "0,8–0,9")]
mid_n = sum(r["n"] for r in mid_rate)
mid_p = sum(r["n"] * r["confirm_rate"] for r in mid_rate) / mid_n * 100
ax.bar([-0.2 + 0.4 + 0.0], [0], width=0.0)
ax.bar([1.8 + 0.0], [0], width=0.0)
ax.set_xticks([0, 1, 2.4, 3.4], ["Precision", "Recall", "", ""])
ax.cla()
labs = ["Precision\nTraining (CV)", "Precision Produktion\nScore 0,5–0,9", "Precision Produktion\nScore ≥ 0,9 (Pilot)"]
vv = [tr_vals[0], mid_p, real_p]
bars = ax.bar(labs, vv, color=[GRAY, ORANGE, AQUA], width=0.55)
for b_, v in zip(bars, vv):
    ax.text(b_.get_x() + b_.get_width() / 2, v + 1.5, f"{v:.0f} %", ha="center", fontsize=9, color=INK2)
ax.set_ylim(0, 112)
ax.set_title("Der Praxistest: Precision im Training vs. im echten Crawl")
ax.set_ylabel("%")
ax.grid(axis="x", visible=False)
KEY["precision_gap"] = {"training_cv_precision": tr_vals[0], "production_mid_0.5_0.9": mid_p, "production_high_pilot": real_p}
save(fig, "23_training_vs_praxis", "Produktion: Referenz = LLM-Urteil (Haiku 4.5), nicht manuell verifiziert.")

# --- extra: sample for manual validation (CSV) ----------------------------------------------------
random.seed(7)
samp = []
for t, n_ in (("llm_confirmed", 40), ("llm_rejected", 40), ("tfidf_high", 40)):
    pool = [d for d in docs if d["tier"] == t]
    samp += random.sample(pool, min(n_, len(pool)))
random.shuffle(samp)
import csv  # noqa: E402

with open(ROOT / "auswertung" / "stichprobe_manuelle_pruefung.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w_ = csv.writer(fh, delimiter=";")
    w_.writerow(["nr", "url", "manuell_ist_modulhandbuch (ja/nein)", "---erst nach der Pruefung ansehen---", "tfidf_score", "llm_urteil", "llm_begruendung"])
    for i, d in enumerate(samp, 1):
        w_.writerow([i, d["url"], "", "", d.get("module_handbook_score"), d["tier"], d.get("llm_reason", "")])

json.dump(KEY, open(DATA / "kennzahlen.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done")
