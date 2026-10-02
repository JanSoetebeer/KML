"""Zusätzliche Grafiken + LaTeX-Zahlenmakros für den Projektbericht.

Baut auf den Ergebnissen von auswertung/ auf (final.jsonl, kennzahlen.json, per_uni_likely.csv).
Eingabedateien, die von Hand gepflegt werden (Platzhalter/Schätzungen anpassen, dann neu laufen lassen):

    bericht/daten/stunden.csv   Wochenstunden (Jan; Sascha wird im Bericht separat eingetragen)
    bericht/daten/kosten.csv    Kosten je Posten (Status: schaetzung | beleg)
    bericht/daten/s3_objekte.csv  Auflistung des S3-Buckets (aws s3 ls --recursive), siehe README

Aufruf (aus dem Repo-Root):

    .venv\\Scripts\\python bericht\\make_report_charts.py

Schreibt PNGs nach bericht/bilder/ und bericht/zahlen.tex (\\newcommand je Kennzahl).
"""
import csv
import json
import math
import re
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BER = ROOT / "bericht"
AUSW = ROOT / "auswertung"
IMG = BER / "bilder"
IMG.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
GRAY = "#9a9a96"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2dd"
PHASE_COL = {"P1": BLUE, "P2": AQUA, "P3": YELLOW, "P4": VIOLET}

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "text.color": INK,
})


def de(n, nd=0):
    """Deutsche Zahlenformatierung: 1.234,5"""
    s = f"{n:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def save(fig, name):
    fig.savefig(IMG / f"{name}.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("chart", name)


def bar_labels(ax, bars, f=lambda v: de(v), pad=0.0, horizontal=False, color=INK2):
    for b in bars:
        if horizontal:
            ax.text(b.get_width() + pad, b.get_y() + b.get_height() / 2, f(b.get_width()),
                    va="center", fontsize=8.5, color=color)
        else:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + pad, f(b.get_height()),
                    ha="center", va="bottom", fontsize=8.5, color=color)


# ---------------------------------------------------------------- Daten laden -------------
docs = [json.loads(l) for l in open(AUSW / "data" / "final.jsonl", encoding="utf-8")]
KEY = json.load(open(AUSW / "data" / "kennzahlen.json", encoding="utf-8"))
Z = {}  # LaTeX-Makros

LIKELY = {"llm_confirmed", "tfidf_high", "tfidf_other"}  # "erweiterte Liste" wie in der Abschlussauswertung


def is_likely(d):
    # erweiterte Liste = LLM bestätigt + TF-IDF >= 0,9 (nicht geprüft) – "tfidf_other" (Aug-Lauf) zählt dort nicht
    return d["tier"] in ("llm_confirmed", "tfidf_high")


likely = [d for d in docs if is_likely(d)]
strict = [d for d in docs if d["tier"] == "llm_confirmed"]

# ---------------------------------------------------------------- S3-Volumen ----------------
s3 = {}
s3_total_bytes = 0
s3_path = BER / "daten" / "s3_objekte.csv"
if s3_path.exists():
    with open(s3_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s3[r["key"]] = int(r["size"])
            s3_total_bytes += int(r["size"])


def size_of(d):
    return s3.get(d.get("s3_key", ""), None)


# ---------------------------------------------------------------- 1) Wochenstunden ----------
stunden = list(csv.DictReader(open(BER / "daten" / "stunden.csv", encoding="utf-8")))
fig, ax = plt.subplots(figsize=(9.2, 3.8))
x = np.arange(len(stunden))
vals = [float(r["stunden_jan"]) for r in stunden]
cols = [PHASE_COL[r["phase"]] for r in stunden]
bars = ax.bar(x, vals, color=cols, width=0.72)
bar_labels(ax, [b for b, v in zip(bars, vals) if v > 0], f=lambda v: de(v), pad=0.25)
ax.set_xticks(x)
ax.set_xticklabels([f"KW {r['kw']}" for r in stunden], rotation=60, fontsize=8.5, ha="right")
ax.set_ylabel("geschätzte Stunden (Jan)")
ax.set_title("Arbeitsaufwand pro Kalenderwoche (Schätzung)")
from matplotlib.patches import Patch  # noqa: E402

phase_names = {"P1": "Phase 1: Prototyp & AWS-Grundlage", "P2": "Phase 2: ML & Plattform",
               "P3": "Phase 3: Großlauf & Recall-Analyse", "P4": "Phase 4: Deep Run & LLM-Bereinigung"}
ax.legend(handles=[Patch(color=PHASE_COL[k], label=v) for k, v in phase_names.items()], fontsize=8.5, loc="upper left", bbox_to_anchor=(0.43, 1.0))
ax.grid(axis="x", visible=False)
save(fig, "B01_stunden_pro_woche")
Z["StundenJan"] = de(sum(vals), 0)

# kumuliert je Phase
ph_sum = defaultdict(float)
for r in stunden:
    ph_sum[r["phase"]] += float(r["stunden_jan"])
for k, v in ph_sum.items():
    Z["StundenPhase" + {"P1": "Eins", "P2": "Zwei", "P3": "Drei", "P4": "Vier"}[k]] = de(v, 0)

# ---------------------------------------------------------------- 2) Kosten -----------------
kosten = list(csv.DictReader(open(BER / "daten" / "kosten.csv", encoding="utf-8")))
order = sorted(kosten, key=lambda r: -float(r["usd"]))
fig, ax = plt.subplots(figsize=(8.6, 3.9))
y = np.arange(len(order))[::-1]
for yi, r in zip(y, order):
    est = r["status"] == "schaetzung"
    ax.barh(yi, float(r["usd"]), color=BLUE if not est else "#a9c8ee", edgecolor=BLUE, hatch="//" if est else None,
            height=0.66)
    ax.text(float(r["usd"]) + 1.0, yi, f"{de(float(r['usd']), 0)} $" + (" (Schätzung)" if est else ""),
            va="center", fontsize=8.5, color=INK2)
ax.set_yticks(y)
ax.set_yticklabels([r["posten"] for r in order], fontsize=9)
ax.set_xlabel("US-Dollar (gesamt über Projektlaufzeit)")
ax.set_title("Kosten nach Posten (vorläufig – Abrechnung ausstehend)")
ax.set_xlim(0, max(float(r["usd"]) for r in order) * 1.32)
ax.grid(axis="y", visible=False)
save(fig, "B02_kosten")
tot = sum(float(r["usd"]) for r in kosten)
Z["KostenGesamt"] = de(tot, 0)
for r in kosten:
    Z["Kosten" + re.sub(r"[^A-Za-z]", "", r["id"])] = de(float(r["usd"]), 0)

# ---------------------------------------------------------------- 3) Verlauf Abdeckung/Positive
steps = [
    ("Aug-Lauf\n(Schw. 0,65)", 261, 11579),
    ("Schwelle\n0,50", 271, 13912),
    ("Seeds-\nonly", 314, 14133),
    ("Eval-\nFix", 303, 13565),
    ("Deep\nRun", 321, 43270),
]
final_steps = [("Endstand\nerweitert*", KEY["unis_with_mh_likely"], KEY["final_likely_listed"]),
               ("Endstand\nstreng**", KEY["unis_with_mh_strict"], KEY["final_strict"])]
fig, axs = plt.subplots(1, 2, figsize=(10, 4.0))
labs = [s[0] for s in steps] + [s[0] for s in final_steps]
cov = [s[1] for s in steps] + [s[1] for s in final_steps]
pos = [s[2] for s in steps] + [s[2] for s in final_steps]
colr = [GRAY] * len(steps) + [AQUA, BLUE]
b = axs[0].bar(range(len(cov)), cov, color=colr, width=0.7)
bar_labels(axs[0], b, pad=3)
axs[0].set_xticks(range(len(cov)))
axs[0].set_xticklabels(labs, fontsize=7.2)
axs[0].set_ylim(0, 440)
axs[0].axhline(KEY["unis_total"], color=ORANGE, lw=1, ls="--")
axs[0].text(len(cov) - 0.5, KEY["unis_total"] + 6, f"Hochschulen gesamt: {KEY['unis_total']}", ha="right", fontsize=8, color=ORANGE)
axs[0].set_title("Hochschulen mit ≥ 1 Treffer")
b = axs[1].bar(range(len(pos)), pos, color=colr, width=0.7)
bar_labels(axs[1], b, pad=600)
axs[1].set_xticks(range(len(pos)))
axs[1].set_xticklabels(labs, fontsize=7.2)
axs[1].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: de(v)))
axs[1].set_title("Gelistete Positive")
fig.text(0.01, -0.06, "Grau: TF-IDF-Positive ohne LLM-Prüfung (Precision im Deep Run ≈ 60 %). "
         "*TF-IDF ≥ 0,9 oder LLM-bestätigt  **nur LLM-bestätigt.", fontsize=7.5, color=INK2)
fig.tight_layout()
save(fig, "B03_verlauf_abdeckung")

# ---------------------------------------------------------------- 4) Läufe: Dauer, Durchsatz -
runs = [
    ("Aug-Lauf\n(12.08.)", 6.3, 65944, 404),
    ("Seeds-only\n(03.09.)", 0.06, 431, 84),
    ("Deep Run\n(16./17.09.)", 12.0, 132193, 232),
]
fig, axs = plt.subplots(1, 3, figsize=(10.4, 3.3))
names = [r[0] for r in runs]
b = axs[0].bar(names, [r[1] for r in runs], color=[BLUE, GRAY, VIOLET])
bar_labels(axs[0], b, f=lambda v: de(v, 1), pad=0.2)
axs[0].set_title("Laufzeit [h]")
b = axs[1].bar(names, [r[2] for r in runs], color=[BLUE, GRAY, VIOLET])
bar_labels(axs[1], b, pad=2500)
axs[1].set_title("PDFs heruntergeladen")
axs[1].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: de(v)))
rate = [r[2] / r[1] if r[1] > 0.5 else None for r in runs]
b = axs[2].bar(names, [v or 0 for v in rate], color=[BLUE, GRAY, VIOLET])
bar_labels(axs[2], [bb for bb, v in zip(b, rate) if v], pad=250)
axs[2].text(1, 400, "zu kurz für\nDurchsatzangabe", ha="center", fontsize=8, color=INK2)
axs[2].set_title("PDFs pro Stunde (Mittel)")
axs[2].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: de(v)))
for a in axs:
    a.tick_params(axis="x", labelsize=8)
fig.tight_layout()
save(fig, "B04_laeufe_dauer")
Z["DauerAug"] = "6,3"
Z["DauerDeep"] = "12,0"
Z["RateAug"] = de(65944 / 6.3, 0)
Z["RateDeep"] = de(132193 / 12.0, 0)

# ---------------------------------------------------------------- 5) Datenmenge -------------
if s3:
    per_day = Counter()
    for k, s in s3.items():
        if k.startswith("scraped/"):
            pass
    # Volumen je Lauf aus S3-Zeitstempeln
    day_bytes = Counter()
    with open(s3_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["key"].startswith("scraped/"):
                day_bytes[r["date"]] += int(r["size"])
    run_vol = {"Aug-Lauf": day_bytes.get("2026-08-12", 0) / 1e9,
               "Seeds-Läufe": (day_bytes.get("2026-09-02", 0) + day_bytes.get("2026-09-03", 0)) / 1e9,
               "Deep Run": (day_bytes.get("2026-09-16", 0) + day_bytes.get("2026-09-17", 0)) / 1e9}
    # Dateigrößen der eindeutigen Dokumente
    sizes = [size_of(d) for d in docs if size_of(d)]
    sizes_mh = [size_of(d) for d in likely if size_of(d)]
    sizes_other = [size_of(d) for d in docs if size_of(d) and not is_likely(d)]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.7), gridspec_kw={"width_ratios": [1, 1.5]})
    b = axs[0].bar(list(run_vol), list(run_vol.values()), color=[BLUE, GRAY, VIOLET])
    bar_labels(axs[0], b, f=lambda v: de(v, 1) + " GB", pad=1.5)
    axs[0].set_title("Gespeicherte Daten je Lauf")
    axs[0].set_ylabel("GB (S3, inkl. Duplikate)")
    axs[0].tick_params(axis="x", labelsize=8.5)
    bins = np.logspace(3, 8, 45)
    axs[1].hist(np.array(sizes_other) , bins=bins, color=GRAY, alpha=0.75, label="übrige PDFs")
    axs[1].hist(np.array(sizes_mh), bins=bins, color=AQUA, alpha=0.85, label="gelistete Modulhandbücher")
    axs[1].set_xscale("log")
    axs[1].set_xticks([1e3, 1e4, 1e5, 1e6, 1e7, 1e8])
    axs[1].set_xticklabels(["1 KB", "10 KB", "100 KB", "1 MB", "10 MB", "100 MB"])
    axs[1].axvline(statistics.median(sizes_mh), color=AQUA, ls="--", lw=1)
    axs[1].set_title("Dateigrößenverteilung der PDFs")
    axs[1].set_ylabel("Anzahl")
    axs[1].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: de(v)))
    axs[1].legend(fontsize=8.5)
    fig.tight_layout()
    save(fig, "B05_datenmenge")
    uniq_bytes = sum(sizes)
    Z["SpeicherObjekte"] = de(len(s3))
    Z["SpeicherGB"] = de(s3_total_bytes / 1e9, 1)
    Z["SpeicherGiB"] = de(s3_total_bytes / 2**30, 1)
    Z["UniqueGB"] = de(uniq_bytes / 1e9, 1)
    Z["MedianMBMH"] = de(statistics.median(sizes_mh) / 1e6, 2)
    Z["MedianMBAll"] = de(statistics.median(sizes) / 1e6, 2)
    Z["MeanMB"] = de(statistics.mean(sizes) / 1e6, 2)
    Z["MHVolumeGB"] = de(sum(sizes_mh) / 1e9, 1)
    Z["MHStrictVolumeGB"] = de(sum(size_of(d) or 0 for d in strict) / 1e9, 1)
    Z["DupVolumePct"] = de(100 * (1 - uniq_bytes / s3_total_bytes), 0)
    mean_mb_mh = statistics.mean(sizes_mh) / 1e6
    mean_mb_all = statistics.mean(sizes) / 1e6
else:
    mean_mb_mh = mean_mb_all = 0.8

# ---------------------------------------------------------------- 6) Tiefe (Näherung) -------
def depth(u):
    p = urlparse(u).path.strip("/")
    return 0 if not p else len(p.split("/"))


src_depth_all, src_depth_mh, doc_depth_mh = Counter(), Counter(), Counter()
for d in docs:
    sp = d.get("source_page") or ""
    if sp and sp != "discovery":
        src_depth_all[min(depth(sp), 10)] += 1
for d in likely:
    sp = d.get("source_page") or ""
    if sp and sp != "discovery":
        src_depth_mh[min(depth(sp), 10)] += 1
    doc_depth_mh[min(depth(d["url"]), 12)] += 1
ks = list(range(0, 11))
tot_all = sum(src_depth_all.values())
tot_mh = sum(src_depth_mh.values())
fig, ax = plt.subplots(figsize=(8.6, 3.6))
w = 0.38
ax.bar(np.array(ks) - w / 2, [100 * src_depth_all[k] / tot_all for k in ks], w, color=GRAY, label="alle PDFs")
ax.bar(np.array(ks) + w / 2, [100 * src_depth_mh[k] / tot_mh for k in ks], w, color=AQUA, label="gelistete Modulhandbücher")
ax.set_xticks(ks)
ax.set_xticklabels([str(k) if k < 10 else "≥10" for k in ks])
ax.set_xlabel("Pfadtiefe der Fundseite (Anzahl URL-Segmente; Näherung für die Klicktiefe)")
ax.set_ylabel("Anteil [%]")
ax.set_title("In welcher Tiefe der Webseiten liegen die Dokumente?")
ax.legend()
save(fig, "B06_tiefe")
mode_all = max(src_depth_all, key=src_depth_all.get)
mode_mh = max(src_depth_mh, key=src_depth_mh.get)
Z["TiefeModusAlle"] = str(mode_all)
Z["TiefeModusMH"] = str(mode_mh)
Z["TiefeMHBisVier"] = de(100 * sum(src_depth_mh[k] for k in range(0, 5)) / tot_mh, 0)

# ---------------------------------------------------------------- 7) klein vs. groß ---------
rows = list(csv.DictReader(open(AUSW / "data" / "per_uni_likely.csv", encoding="utf-8-sig")))
classes = [("<1.000", 0, 1000), ("1.000–5.000", 1000, 5000), ("5.000–15.000", 5000, 15000),
           ("15.000–30.000", 15000, 30000), (">30.000", 30000, 10 ** 9)]
stats = []
for name, lo, hi in classes:
    sel = []
    for r in rows:
        try:
            s = int(float(r["students"]))
        except ValueError:
            continue
        if lo <= s < hi:
            sel.append(r)
    mh = [int(r["mh_positive"]) for r in sel]
    dc = [int(r["docs_total"]) for r in sel]
    stats.append((name, len(sel), statistics.median(mh) if mh else 0, statistics.mean(mh) if mh else 0,
                  statistics.mean(dc) if dc else 0, sum(1 for m in mh if m >= 10) / max(1, len(mh)) * 100))
fig, axs = plt.subplots(1, 3, figsize=(10.4, 3.4))
nm = [f"{s[0]}\n(n={s[1]})" for s in stats]
b = axs[0].bar(nm, [s[3] for s in stats], color=BLUE)
bar_labels(axs[0], b, f=lambda v: de(v, 0), pad=1)
axs[0].set_title("Ø Modulhandbücher je Hochschule")
b = axs[1].bar(nm, [s[4] for s in stats], color=GRAY)
bar_labels(axs[1], b, f=lambda v: de(v, 0), pad=4)
axs[1].set_title("Ø heruntergeladene PDFs je Hochschule")
b = axs[2].bar(nm, [s[5] for s in stats], color=AQUA)
bar_labels(axs[2], b, f=lambda v: de(v, 0) + " %", pad=1)
axs[2].set_title("Anteil Hochschulen mit ≥ 10 Treffern")
for a in axs:
    a.tick_params(axis="x", labelsize=7.2)
fig.text(0.01, -0.05, "Größenklasse = Studierendenzahl der Hochschule laut Hochschulliste (erweiterte Liste).", fontsize=7.5, color=INK2)
fig.tight_layout()
save(fig, "B07_klein_gross")
Z["MHProUniKlein"] = de(stats[0][3], 1)
Z["MHProUniGross"] = de(stats[-2][3], 0)
Z["MHProUniGrossMax"] = de(stats[-1][3], 0)
Z["DocsProUniKlein"] = de(stats[0][4], 0)
Z["DocsProUniGross"] = de(stats[-2][4], 0)

# ---------------------------------------------------------------- 8) Hochrechnung -----------
est_true = KEY["final_likely_estimated_true"]["mid"]
pdfs_now = KEY["docs_total"]
yield_ratio = pdfs_now / est_true            # PDFs je echtem Modulhandbuch
target = 40000                               # Fachschätzung des Betreuers/Projekts (Referenz)
pdfs_proj = target * yield_ratio
llm_share = KEY["llm_reviewed_docs"] / pdfs_now
llm_docs_now = KEY["llm_reviewed_docs"]
llm_cost_now = 75.0
llm_docs_proj = pdfs_proj * llm_share
llm_cost_proj = llm_cost_now * llm_docs_proj / llm_docs_now
gb_now = (sum(s3.values()) / 1e9) if s3 else 154.0
gb_proj = gb_now * pdfs_proj / (s3 and len(s3) or 193000)
fig, axs = plt.subplots(1, 4, figsize=(10.8, 3.3))
pairs = [("PDFs\ngesammelt", pdfs_now / 1e3, pdfs_proj / 1e3, "Tsd."),
         ("Speicher\n(S3)", gb_now, gb_proj, "GB"),
         ("Dokumente\nan LLM", llm_docs_now / 1e3, llm_docs_proj / 1e3, "Tsd."),
         ("LLM-Kosten", llm_cost_now, llm_cost_proj, "$")]
for a, (t, v0, v1, u) in zip(axs, pairs):
    b = a.bar(["Ist", "Hochrechnung\n40.000 MH"], [v0, v1], color=[BLUE, "#a9c8ee"], edgecolor=BLUE)
    b[1].set_hatch("//")
    bar_labels(a, b, f=lambda v, u=u: f"{de(v, 0)} {u}", pad=max(v0, v1) * 0.02)
    a.set_title(t, fontsize=10.5)
    a.set_ylim(0, max(v0, v1) * 1.2)
    a.tick_params(axis="x", labelsize=8)
fig.text(0.01, -0.06, f"Lineare Hochrechnung bei gleichbleibender Ausbeute ({de(yield_ratio, 1)} PDFs je Modulhandbuch). "
         "Da die verbleibenden Handbücher auf schwer erreichbaren Seiten liegen, ist die tatsächliche Ausbeute pro PDF vermutlich schlechter.",
         fontsize=7.5, color=INK2)
fig.tight_layout()
save(fig, "B08_hochrechnung")
Z["Zielwert"] = de(target)
Z["PDFsHochrechnung"] = de(pdfs_proj, 0)
Z["GBHochrechnung"] = de(gb_proj, 0)
Z["LLMDocsHochrechnung"] = de(llm_docs_proj, 0)
Z["LLMKostenHochrechnung"] = de(llm_cost_proj, 0)
Z["PDFsProMH"] = de(yield_ratio, 1)

# ---------------------------------------------------------------- 9) Manueller Aufwand ------
rev_before = KEY["tiers"].get("tfidf_other", 0)  # nur Info
reviewed = KEY["llm_reviewed_docs"]
sec = 30
fig, ax = plt.subplots(figsize=(8.2, 3.2))
items = [("Alle TF-IDF-Positive manuell\nprüfen (Annahme 30 s/Dok.)", reviewed * sec / 3600, GRAY),
         ("Mit LLM-Zweitstufe:\nStichprobe + Verdachtsliste (Annahme 30 s/Dok.)", (120 + 1658) * sec / 3600, BLUE)]
b = ax.barh([i[0] for i in items][::-1], [i[1] for i in items][::-1], color=[i[2] for i in items][::-1])
bar_labels(ax, b, f=lambda v: de(v, 0) + " h", pad=5, horizontal=True)
ax.set_xlabel("Stunden")
ax.set_title("Manueller Prüfaufwand: ohne vs. mit LLM-Zweitstufe (Modellrechnung)")
ax.set_xlim(0, items[0][1] * 1.2)
ax.grid(axis="y", visible=False)
save(fig, "B09_manueller_aufwand")
Z["ManuellOhneH"] = de(reviewed * sec / 3600, 0)
Z["ManuellMitH"] = de((120 + 1658) * sec / 3600, 0)

# ---------------------------------------------------------------- Jahre / Alter -------------
years = []
for d in likely:
    m = re.search(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)", d["filename"])
    if m:
        years.append(int(m.group(1)))
years = [y for y in years if y <= 2027]
cnt = Counter(years)
Z["JahrMin"] = str(min(years))
Z["JahrMedian"] = str(int(statistics.median(years)))
Z["JahrAnteilNeu"] = de(100 * sum(1 for y in years if y >= 2020) / len(years), 0)
Z["JahrAnzahl"] = de(len(years))
Z["JahrMinAnzahl"] = str(cnt[min(years)])
Z["JahreMitte"] = de(sum(1 for y in years if 2015 <= y <= 2019))
Z["JahreAlt"] = de(sum(1 for y in years if y < 2015))

# ---------------------------------------------------------------- Kennzahlen -> Makros ------
K = KEY
Z.update({
    "DocsTotal": de(K["docs_total"]),
    "UnisTotal": str(K["unis_total"]),
    "UnisStrict": str(K["unis_with_mh_strict"]),
    "UnisLikely": str(K["unis_with_mh_likely"]),
    "UnisStrictPct": de(100 * K["unis_with_mh_strict"] / K["unis_total"], 0),
    "UnisLikelyPct": de(100 * K["unis_with_mh_likely"] / K["unis_total"], 0),
    "UnisGeTen": str(K["unis_with_ge10_likely"]),
    "UnisNone": str(K["flags"]["Nach der Bereinigung inkl. ≥ 0,9 ungeprüft"]["no_docs_no_seeds"]),
    "MedianMH": de(K["mh_per_uni_median_likely"], 0),
    "TopTenShare": de(100 * K["top10_unis_share_likely"], 0),
    "LLMReviewed": de(K["llm_reviewed_docs"]),
    "LLMConfirmed": de(K["tiers"]["llm_confirmed"]),
    "LLMRejected": de(K["tiers"]["llm_rejected"]),
    "TfidfHigh": de(K["tiers"]["tfidf_high"]),
    "TfidfOther": de(K["tiers"]["tfidf_other"]),
    "Unresolved": de(K["tiers"]["unresolved"]),
    "TfidfNegative": de(K["tiers"]["tfidf_negative"]),
    "InitialPositive": de(K["initial_tfidf_positive"]),
    "FinalStrict": de(K["final_strict"]),
    "FinalListed": de(K["final_likely_listed"]),
    "EstTrue": de(K["final_likely_estimated_true"]["mid"], 0),
    "EstTrueLow": de(K["final_likely_estimated_true"]["low"], 0),
    "EstTrueHigh": de(K["final_likely_estimated_true"]["high"], 0),
    "PilotN": str(K["pilot"]["n"]),
    "PilotOK": str(K["pilot"]["confirmed"]),
    "PilotPct": de(100 * K["pilot"]["precision"], 1),
    "PilotLo": de(100 * K["pilot"]["ci95"][0], 1),
    "PilotHi": de(100 * K["pilot"]["ci95"][1], 1),
    "DupLikely": de(K["dedup"]["likely_docs"] - K["dedup"]["likely_unique_host_filename"]),
    "UniqueLikely": de(K["dedup"]["likely_unique_host_filename"]),
    "UniqueStrict": de(K["dedup"]["strict_unique_host_filename"]),
    "DupStrict": de(K["dedup"]["strict_docs"] - K["dedup"]["strict_unique_host_filename"]),
    "OCRTotal": de(K["ocr"]["Gescannte PDFs ohne Textebene (Review-Band)"]),
    "OCRDone": de(K["ocr"]["OCR durchgeführt"]),
    "OCRText": de(K["ocr"]["Text per OCR gewonnen"]),
    "OCRLLM": de(K["ocr"]["Score ≥ 0,5 → an LLM"]),
    "OCRConf": de(K["ocr"]["LLM bestätigt"]),
    "RecallMissed": de(K["recall_gap"]["estimated_missed_mh"]),
    "FPTotal": de(K["n_false_positives_by_llm"]),
    "TrainPrec": de(K["precision_gap"]["training_cv_precision"], 1),
    "MidPrec": de(K["precision_gap"]["production_mid_0.5_0.9"], 0),
})
for k, v in K["seg_type"].items():
    pass
# Hochschultyp / Träger
seg = K["seg_type"]
Z["CovUni"] = de(100 * seg["Universität"]["with_mh"] / seg["Universität"]["n"], 0)
Z["CovFH"] = de(100 * seg["Fachhochschule / HAW"]["with_mh"] / seg["Fachhochschule / HAW"]["n"], 0)
Z["CovKunst"] = de(100 * seg["Künstlerische Hochschule"]["with_mh"] / seg["Künstlerische Hochschule"]["n"], 0)
Z["CovVerw"] = de(100 * seg["Verwaltungshochschule"]["with_mh"] / seg["Verwaltungshochschule"]["n"], 0)
tr = K["seg_traeger"]
Z["CovOeff"] = de(100 * tr["öffentlich-rechtlich"]["with_mh"] / tr["öffentlich-rechtlich"]["n"], 0)
Z["CovPriv"] = de(100 * tr["privat"]["with_mh"] / tr["privat"]["n"], 0)
Z["CovKirch"] = de(100 * tr["kirchlich"]["with_mh"] / tr["kirchlich"]["n"], 0)

# ---------------------------------------------------------------- zahlen.tex ----------------
def macro_name(k):
    return "z" + k


with open(BER / "zahlen.tex", "w", encoding="utf-8") as f:
    f.write("% AUTOMATISCH ERZEUGT von bericht/make_report_charts.py - nicht von Hand editieren.\n")
    for k in sorted(Z):
        f.write(f"\\newcommand{{\\{macro_name(k)}}}{{{Z[k]}}}\n")
print("zahlen.tex:", len(Z), "Makros")

# ---------------------------------------------------------------- wochen.tex (Aktivitätstabellen)
with open(BER / "wochen_jan.tex", "w", encoding="utf-8") as f:
    f.write("% AUTOMATISCH ERZEUGT aus daten/stunden.csv\n")
    total = 0.0
    for r in stunden:
        h = float(r["stunden_jan"])
        total += h
        f.write(f"KW\\,{r['kw']} & {r['von']}--{r['bis']} & {r['taetigkeit']} & ca.\\,{de(h, 0)} \\\\\n")
    f.write("\\midrule\n")
    f.write(f"\\multicolumn{{3}}{{l}}{{\\textbf{{Summe (Schätzung)}}}} & \\textbf{{ca.\\,{de(total, 0)}}} \\\\\n")
with open(BER / "wochen_sascha.tex", "w", encoding="utf-8") as f:
    f.write("% AUTOMATISCH ERZEUGT aus daten/stunden.csv - Platzhalter für Sascha Lauk\n")
    for r in stunden:
        f.write(f"KW\\,{r['kw']} & {r['von']}--{r['bis']} & \\saschaCell{{}} & \\saschaCell{{}} \\\\\n")
    f.write("\\midrule\n")
    f.write("\\multicolumn{3}{l}{\\textbf{Summe}} & \\saschaCell{} \\\\\n")

# ---------------------------------------------------------------- Auswertungs-Grafiken kopieren
for p in sorted((AUSW / "charts").glob("*.png")):
    shutil.copy2(p, IMG / p.name)
print("kopiert:", len(list((AUSW / "charts").glob('*.png'))), "Grafiken aus auswertung/charts")
