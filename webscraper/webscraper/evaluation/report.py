"""
Render a :class:`RunEvaluation` to a single self-contained HTML file.

No external assets, no JavaScript libraries — inline CSS and hand-built inline
SVG bar charts — so the report opens anywhere and can be dropped straight into a
thesis appendix or printed to PDF. Theme-aware (light/dark via
``prefers-color-scheme``).
"""

from __future__ import annotations

import html
from typing import Optional

from webscraper.evaluation.schema import MetricSet, RunEvaluation, ScenarioResult, UniversityResult


# --------------------------------------------------------------------------- #
# small formatting helpers
# --------------------------------------------------------------------------- #

def _n(x) -> str:
    """Thousands separator with a thin space (locale-independent)."""
    try:
        return f"{int(round(x)):,}".replace(",", " ")
    except Exception:
        return str(x)


def _pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f} %"


def _f(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# --------------------------------------------------------------------------- #
# inline SVG charts
# --------------------------------------------------------------------------- #

def _bar_chart(pairs, *, height_per_bar=26, width=560, value_fmt=_n, color_var="--accent",
               max_label=26) -> str:
    """Horizontal bar chart. ``pairs`` = list[(label, value)]."""
    if not pairs:
        return "<p class='muted'>keine Daten</p>"
    vmax = max((v for _, v in pairs), default=1) or 1
    label_w = 210
    bar_w = width - label_w - 60
    h = height_per_bar * len(pairs) + 10
    rows = []
    for i, (label, value) in enumerate(pairs):
        y = i * height_per_bar + 8
        bw = max(1, bar_w * (value / vmax)) if value else 0
        lab = _esc(label if len(str(label)) <= max_label else str(label)[: max_label - 1] + "…")
        rows.append(
            f'<text x="0" y="{y + 13}" class="bl">{lab}</text>'
            f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="16" rx="3" '
            f'fill="var({color_var})"></rect>'
            f'<text x="{label_w + bw + 6:.1f}" y="{y + 13}" class="bv">{value_fmt(value)}</text>'
        )
    return (f'<svg viewBox="0 0 {width} {h}" class="chart" role="img" '
            f'preserveAspectRatio="xMinYMin meet">' + "".join(rows) + "</svg>")


def _stacked_decision_bar(m: MetricSet, width=560) -> str:
    """One stacked bar showing positive / review / negative share of documents."""
    total = m.docs_total or 1
    seg = [("positiv", m.mh_positive, "--pos"),
           ("review", m.mh_review, "--rev"),
           ("negativ", m.mh_negative, "--neg")]
    x = 0.0
    parts, legend = [], []
    for name, val, cvar in seg:
        w = width * (val / total)
        parts.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="34" fill="var({cvar})"></rect>')
        x += w
        legend.append(
            f'<span class="lg"><i style="background:var({cvar})"></i>{name}: '
            f'<b>{_n(val)}</b> ({_pct(val/total)})</span>')
    svg = (f'<svg viewBox="0 0 {width} 34" class="chart" role="img" '
           f'preserveAspectRatio="none" style="height:34px">' + "".join(parts) + "</svg>")
    return svg + '<div class="legend">' + "".join(legend) + "</div>"


# --------------------------------------------------------------------------- #
# building blocks
# --------------------------------------------------------------------------- #

def _kpi(value: str, label: str, sub: str = "", tone: str = "") -> str:
    cls = f"kpi {tone}".strip()
    subhtml = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f'<div class="{cls}"><div class="kpi-val">{value}</div><div class="kpi-lab">{label}</div>{subhtml}</div>'


def _scenario_row(sc: ScenarioResult) -> str:
    m = sc.metrics
    exp = ""
    if sc.expectation is not None:
        ok = sc.expectation.passed
        badge = "pass" if ok else ("fail" if ok is False else "na")
        sym = "✓" if ok else ("✗" if ok is False else "–")
        exp = f'<span class="badge {badge}" title="{_esc(sc.expectation.description)}">{sym}</span>'
    return (
        "<tr>"
        f'<td class="lbl">{_esc(sc.label)} {exp}</td>'
        f"<td>{_n(m.n_unis)}</td>"
        f"<td>{_n(m.n_unis_with_coverage)}<span class='muted'> ({_pct(m.coverage_rate,0)})</span></td>"
        f"<td>{_n(m.docs_total)}</td>"
        f"<td>{_n(m.mh_positive)}</td>"
        f"<td>{_n(m.mh_review)}</td>"
        f"<td>{_pct(m.positive_rate)}</td>"
        f"<td>{_f(m.mh_per_uni_mean)}</td>"
        f"<td>{_f(m.mh_per_uni_median,0)}</td>"
        "</tr>"
    )


def _deepdive_card(sc: ScenarioResult, uni: Optional[UniversityResult]) -> str:
    m = sc.metrics
    meta = ""
    if uni is not None:
        meta = (f'<div class="dd-meta">{_esc(uni.uni_type)} · {_esc(uni.traeger)} · '
                f'{_esc(uni.bundesland)} · {_n(uni.students) if uni.students else "?"} Studierende · '
                f'<code>{_esc(uni.domain)}</code></div>')
    exp = ""
    if sc.expectation is not None:
        ok = sc.expectation.passed
        cls = "pass" if ok else ("fail" if ok is False else "na")
        txt = "erfüllt" if ok else ("NICHT erfüllt" if ok is False else "n/a")
        exp = (f'<div class="dd-exp {cls}"><b>Erwartung:</b> {_esc(sc.expectation.description)} '
               f'→ <b>{txt}</b> (Positive={_n(m.mh_positive)}, Ziel {sc.expectation.op} '
               f'{_n(sc.expectation.value)})</div>')
    years = ""
    if uni is not None and uni.year_hist:
        yr = ", ".join(f"{y}: {c}" for y, c in sorted(uni.year_hist.items()))
        years = (f'<div class="dd-years"><b>Jahrgänge (aus Dateinamen):</b> '
                 f'{_esc(uni.year_min)}–{_esc(uni.year_max)} &nbsp; <span class="muted">{_esc(yr)}</span></div>')
    return (
        '<div class="card dd">'
        f'<h4>{_esc(sc.label)}</h4>{meta}'
        '<div class="dd-kpis">'
        f'{_kpi(_n(m.docs_total), "PDFs geladen")}'
        f'{_kpi(_n(m.mh_positive), "MH positiv", tone="tone-pos")}'
        f'{_kpi(_n(m.mh_review), "Review", tone="tone-rev")}'
        f'{_kpi(_pct(m.positive_rate), "Positiv-Quote")}'
        "</div>"
        f'{_stacked_decision_bar(m)}'
        f"{exp}{years}"
        "</div>"
    )


def _zero_coverage_table(unis: list[UniversityResult]) -> str:
    """Universities that were crawled (>=1 doc) but yielded 0 handbooks, plus
    those that produced no documents at all — the two failure modes."""
    crawled_zero = [u for u in unis if u.matched and u.metrics.mh_positive == 0]
    no_data = [u for u in unis if not u.matched]
    crawled_zero.sort(key=lambda u: (-u.metrics.docs_total))
    no_data.sort(key=lambda u: (u.uni_type, u.name))

    def rows(items, show_docs):
        out = []
        for u in items:
            docs = (f"<td>{_n(u.metrics.docs_total)}</td>"
                    f"<td>{_n(u.metrics.mh_review)}</td>") if show_docs else "<td>–</td><td>–</td>"
            out.append(
                f'<tr><td class="lbl">{_esc(u.name)}</td>'
                f"<td>{_esc(u.uni_type)}</td><td>{_esc(u.traeger)}</td>"
                f"<td>{_esc(u.bundesland)}</td>{docs}"
                f"<td><code>{_esc(u.domain)}</code></td></tr>")
        return "".join(out)

    head = ("<tr><th>Hochschule</th><th>Typ</th><th>Träger</th><th>Land</th>"
            "<th>PDFs</th><th>Review</th><th>Domain</th></tr>")
    return (
        f'<h3>A) Gecrawlt, aber 0 Modulhandbücher erkannt <span class="muted">({len(crawled_zero)})</span></h3>'
        '<p class="muted">Der Crawler war auf der Domain, hat PDFs geladen — aber der Klassifikator '
        'erkannte keins als Modulhandbuch (echtes Fehlen, PDFs hinter Login/JS, oder Klassifikator-Miss).</p>'
        f'<div class="scroll"><table class="grid">{head}{rows(crawled_zero, True)}</table></div>'
        f'<h3>B) Keine Dokumente gefunden <span class="muted">({len(no_data)})</span></h3>'
        '<p class="muted">Kein einziges PDF von der Domain geladen — Seed-URL tot/umgezogen, robots/Blockade, '
        'reine JS-Seite, oder Inhalte auf Fremd-Domain (Login-Portal).</p>'
        f'<div class="scroll"><table class="grid">{head}{rows(no_data, False)}</table></div>'
    )


# --------------------------------------------------------------------------- #
# top-level render
# --------------------------------------------------------------------------- #

def render_html(ev: RunEvaluation) -> str:
    g = ev.global_metrics
    th = ev.throughput
    tp = ev.temporal
    upper_bound = g.mh_positive + g.mh_review  # if every review item were a handbook

    # ---- KPI band ----------------------------------------------------------
    cov_ratio = g.mh_positive / ev.expected_total if ev.expected_total else 0
    kpis = "".join([
        _kpi(_n(g.mh_positive), "Modulhandbücher (positiv)", "automatic_positive", "tone-pos"),
        _kpi(_pct(cov_ratio, 0), f"von ~{_n(ev.expected_total)} erwartet", "Recall-Schätzung", "tone-warn"),
        _kpi(_n(g.mh_review), "Review-Band", "unsichere Fälle", "tone-rev"),
        _kpi(_n(g.docs_total), "PDFs gesamt geladen"),
        _kpi(f"{_n(g.n_unis_with_coverage)}/{_n(g.n_unis)}",
             "Hochschulen mit ≥1 MH", _pct(g.coverage_rate, 0) + " Coverage"),
        _kpi(_n(ev.n_universities_input - g.n_unis_with_coverage),
             "Hochschulen mit 0 MH", "Lücken", "tone-warn"),
        _kpi(_f(th.docs_per_hour, 0), "PDFs/Stunde", f"{_f(th.docs_per_second,2)} Docs/s"),
        _kpi(_f(th.run_span_s / 3600, 1) + " h", "Laufzeit (elapsed)",
             f"{_n(th.n_jobs)} Crawl-Jobs"),
    ])

    # ---- scenario table ----------------------------------------------------
    order = {"global": 0, "segment": 1, "university": 2}
    seg_rows = "".join(_scenario_row(sc) for sc in ev.scenarios if sc.kind in ("global", "segment"))
    scen_head = ("<tr><th>Szenario</th><th>Hoch­schulen</th><th>mit ≥1 MH</th>"
                 "<th>PDFs</th><th>MH+</th><th>Review</th><th>Positiv-Quote</th>"
                 "<th>MH/Uni ⌀</th><th>Median</th></tr>")

    # ---- deep dives --------------------------------------------------------
    dom_index = {u.domain: u for u in ev.universities if u.domain}
    dd_cards = "".join(
        _deepdive_card(sc, dom_index.get(sc.key.split(":", 1)[1]))
        for sc in ev.scenarios if sc.kind == "university")

    # ---- distribution of MH per uni (histogram) ----------------------------
    covered = [u for u in ev.universities if u.matched]
    dist_buckets = [("0", 0, 1), ("1–4", 1, 5), ("5–9", 5, 10), ("10–24", 10, 25),
                    ("25–49", 25, 50), ("50–99", 50, 100), ("100+", 100, 10**9)]
    dist_pairs = []
    for label, lo, hi in dist_buckets:
        c = sum(1 for u in covered if lo <= u.metrics.mh_positive < hi)
        dist_pairs.append((f"{label} MH", c))

    # ---- temporal ----------------------------------------------------------
    year_pairs = [(str(y), c) for y, c in tp.year_hist.items()]
    timeline_pairs = [(k[11:] + ":00", v) for k, v in tp.crawl_timeline.items()]

    # ---- segment charts (coverage by Träger / Typ) -------------------------
    def seg_chart(dim):
        pairs = [(sc.label.split(": ", 1)[-1], sc.metrics.coverage_rate * 100)
                 for sc in ev.scenarios if sc.dimension == dim]
        return _bar_chart(pairs, value_fmt=lambda v: f"{v:.0f}%", color_var="--accent2")
    cov_by_traeger = seg_chart("traeger")
    cov_by_type = seg_chart("uni_type")

    # ---- top universities --------------------------------------------------
    top = sorted(covered, key=lambda u: -u.metrics.mh_positive)[:15]
    top_pairs = [(u.name, u.metrics.mh_positive) for u in top]

    upper_note = (f"Bei Annahme, dass alle {_n(g.mh_review)} Review-Dokumente echte "
                  f"Modulhandbücher sind, läge die Obergrenze bei <b>{_n(upper_bound)}</b> "
                  f"({_pct(upper_bound/ev.expected_total,0)} des Erwartungswerts).")

    return _TEMPLATE.format(
        css=_CSS,
        run_id=_esc(ev.run_id),
        generated=_esc(ev.generated_at[:19].replace("T", " ")),
        manifest=_esc(ev.manifest_path.split("/")[-1].split("\\")[-1]),
        csv=_esc(ev.university_csv.split("/")[-1].split("\\")[-1]),
        n_records=_n(ev.n_manifest_records),
        kpis=kpis,
        global_decision_bar=_stacked_decision_bar(g),
        upper_note=upper_note,
        scen_head=scen_head,
        seg_rows=seg_rows,
        dd_cards=dd_cards,
        cov_by_traeger=cov_by_traeger,
        cov_by_type=cov_by_type,
        dist_chart=_bar_chart(dist_pairs, color_var="--accent"),
        top_chart=_bar_chart(top_pairs, width=620, max_label=40),
        zero_tables=_zero_coverage_table(ev.universities),
        year_chart=_bar_chart(year_pairs, color_var="--pos") if year_pairs else "<p class='muted'>—</p>",
        year_min=_esc(tp.year_min), year_max=_esc(tp.year_max),
        n_with_year=_n(tp.n_with_year), n_without_year=_n(tp.n_without_year),
        timeline_chart=_bar_chart(timeline_pairs, color_var="--accent2",
                                  value_fmt=_n, height_per_bar=20),
        tp_docsps=_f(th.docs_per_second, 2),
        tp_docsph=_n(th.docs_per_hour),
        tp_posph=_n(th.positives_per_hour),
        tp_span=_f(th.run_span_s / 3600, 2),
        tp_jobs=_n(th.n_jobs),
        tp_unimedian=_f(th.uni_span_median_s, 0),
        tp_unimean=_f(th.uni_span_mean_s, 0),
        tp_note=_esc(th.note),
        est_411=_f(th.run_span_s / 3600, 1),
        est_1000=_f((th.run_span_s / max(ev.n_universities_input, 1)) * 1000 / 3600, 1),
        classifier_note=_esc(ev.classifier_note),
        n_input=_n(ev.n_universities_input),
        n_matched=_n(g.n_unis_with_data),
        n_unmatched=_n(len(ev.unmatched_domains)),
    )


# --------------------------------------------------------------------------- #
# template + styles
# --------------------------------------------------------------------------- #

_CSS = """
:root{
  --bg:#f7f8fa; --card:#ffffff; --ink:#1a1f2b; --muted:#6b7280; --line:#e5e7eb;
  --accent:#2563eb; --accent2:#0891b2;
  --pos:#16a34a; --rev:#d97706; --neg:#cbd5e1;
  --tone-pos:#dcfce7; --tone-rev:#fef3c7; --tone-warn:#fee2e2;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme=light]){
    --bg:#0e1116; --card:#161b22; --ink:#e6edf3; --muted:#9aa4b2; --line:#283039;
    --accent:#4f8cff; --accent2:#22b8cf; --neg:#3a4452;
    --tone-pos:#0f3d24; --tone-rev:#4a3410; --tone-warn:#4c1d1d;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:20px;margin:40px 0 14px;
  padding-bottom:6px;border-bottom:2px solid var(--line)}
h3{font-size:16px;margin:22px 0 8px} h4{margin:0 0 6px;font-size:16px}
.sub{color:var(--muted);margin:0 0 4px}
code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px;font-size:.85em}
.muted{color:var(--muted)} .muted.sm{font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi-val{font-size:24px;font-weight:700;line-height:1.1}
.kpi-lab{font-size:13px;color:var(--muted);margin-top:3px}
.kpi-sub{font-size:12px;color:var(--muted);margin-top:2px;opacity:.85}
.kpi.tone-pos{background:var(--tone-pos)} .kpi.tone-rev{background:var(--tone-rev)}
.kpi.tone-warn{background:var(--tone-warn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.grid{width:100%;border-collapse:collapse;font-size:13.5px}
.grid th,.grid td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
.grid th{color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--card)}
.grid td.lbl,.grid th:first-child{text-align:left}
.grid tr:hover td{background:rgba(127,127,127,.06)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;max-height:520px;overflow-y:auto}
.chart{width:100%;height:auto;overflow:visible}
.chart .bl{fill:var(--ink);font-size:12px} .chart .bv{fill:var(--muted);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:8px;font-size:13px;color:var(--muted)}
.lg i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:middle}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.dd-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.dd .dd-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}
.dd .kpi{padding:9px 11px} .dd .kpi-val{font-size:18px}
.dd-meta{color:var(--muted);font-size:13px;margin-bottom:4px}
.dd-exp{margin-top:10px;padding:8px 11px;border-radius:8px;font-size:13.5px}
.dd-exp.pass{background:var(--tone-pos)} .dd-exp.fail{background:var(--tone-warn)}
.dd-exp.na{background:rgba(127,127,127,.1)}
.dd-years{margin-top:8px;font-size:13px}
.badge{display:inline-block;min-width:18px;text-align:center;border-radius:5px;padding:0 5px;
  font-weight:700;font-size:12px}
.badge.pass{background:var(--pos);color:#fff} .badge.fail{background:#dc2626;color:#fff}
.badge.na{background:var(--neg);color:var(--ink)}
.callout{background:var(--card);border-left:4px solid var(--accent);border-radius:8px;
  padding:12px 16px;margin:14px 0}
.foot{margin-top:50px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:14px}
@media(max-width:760px){.two,.dd-grid{grid-template-columns:1fr}.dd .dd-kpis{grid-template-columns:repeat(2,1fr)}}
"""

_TEMPLATE = """<meta charset="utf-8">
<title>Crawl-Run Evaluation — Modulhandbücher</title>
<style>{css}</style>
<div class="wrap">

<h1>Evaluation des Modulhandbuch-Crawls</h1>
<p class="sub">Run <code>{run_id}</code> · erstellt {generated} · Manifest <code>{manifest}</code>
 · Hochschul-Liste <code>{csv}</code> · {n_records} Dokument-Datensätze</p>

<div class="kpis">{kpis}</div>
<div class="callout">{upper_note}</div>

<h2>1 · Gesamtergebnis &amp; Klassifikation</h2>
<div class="card">
  <p class="muted">Verteilung aller geladenen PDFs auf die drei Klassifikator-Entscheidungen.</p>
  {global_decision_bar}
</div>

<h2>2 · Szenario-Vergleich (einheitliche Metriken)</h2>
<p class="muted">Jede Zeile nutzt dieselbe Metrik-Definition, dadurch direkt vergleichbar.
 <b>MH+</b> = automatic_positive · <b>Positiv-Quote</b> = MH+ / geladene PDFs · <b>Coverage</b> = Anteil Hochschulen mit ≥1 MH.</p>
<div class="scroll"><table class="grid">{scen_head}{seg_rows}</table></div>
<div class="two" style="margin-top:16px">
  <div class="card"><h3>Coverage nach Träger</h3>{cov_by_traeger}</div>
  <div class="card"><h3>Coverage nach Hochschultyp</h3>{cov_by_type}</div>
</div>

<h2>3 · Deep Dives (Einzelhochschulen)</h2>
<p class="muted">Gezielte Prüfszenarien inkl. Erwartungsabgleich (✓/✗).</p>
<div class="dd-grid">{dd_cards}</div>

<h2>4 · Verteilung: „ein paar bei vielen, alle bei keiner"</h2>
<div class="two">
  <div class="card"><h3>Hochschulen nach Anzahl gefundener MH</h3>
    <p class="muted sm">Von den {n_matched} gecrawlten Hochschulen — wie viele MH pro Hochschule?</p>
    {dist_chart}</div>
  <div class="card"><h3>Top-15 Hochschulen (meiste MH)</h3>{top_chart}</div>
</div>

<h2>5 · Lückenanalyse: Wo werden keine MH gefunden?</h2>
{zero_tables}

<h2>6 · Zeitliche Analyse (Jahrgänge der Modulhandbücher)</h2>
<div class="two">
  <div class="card"><h3>Jahrgang laut Dateiname (nur Positive)</h3>
    <p class="muted sm">Ältestes {year_min}, neuestes {year_max}. Mit Jahr im Namen: {n_with_year},
      ohne erkennbares Jahr: {n_without_year}.</p>
    {year_chart}</div>
  <div class="card"><h3>Crawl-Verlauf (PDFs je Stunde)</h3>{timeline_chart}</div>
</div>

<h2>7 · Geschwindigkeit &amp; Hochrechnung</h2>
<div class="kpis">
  <div class="kpi"><div class="kpi-val">{tp_docsps}</div><div class="kpi-lab">PDFs / Sekunde</div></div>
  <div class="kpi"><div class="kpi-val">{tp_docsph}</div><div class="kpi-lab">PDFs / Stunde</div></div>
  <div class="kpi"><div class="kpi-val">{tp_posph}</div><div class="kpi-lab">MH+ / Stunde</div></div>
  <div class="kpi"><div class="kpi-val">{tp_span} h</div><div class="kpi-lab">Laufzeit gesamt</div></div>
  <div class="kpi"><div class="kpi-val">{tp_unimedian} s</div><div class="kpi-lab">Median Crawl-Dauer / Uni</div><div class="kpi-sub">⌀ {tp_unimean} s · {tp_jobs} Jobs</div></div>
</div>
<div class="card">
  <b>Hochrechnung für künftige Runs</b> (bei gleicher Parallelität):
  <ul>
    <li>{n_input} Hochschulen ≈ <b>{est_411} h</b> (gemessen)</li>
    <li>1.000 Hochschulen ≈ <b>{est_1000} h</b> (lineare Extrapolation)</li>
  </ul>
  <p class="muted sm">{tp_note}</p>
</div>

<div class="foot">
  <p><b>Methodik:</b> Join Manifest ↔ Hochschul-Liste über die registrierte Domain (letzte zwei Labels).
   Eingang: {n_input} Hochschulen · davon mit Crawl-Daten: {n_matched} · Manifest-Domains ohne Listen-Treffer: {n_unmatched}.
   {classifier_note}</p>
  <p>„Erwartet ~40k" ist eine Domänen-Schätzung der real existierenden Modulhandbücher und dient nur als
   Recall-Referenz; das Review-Band ist potenzieller Zusatz-Recall. Positiv-Quote ≠ Präzision im ML-Sinn
   (keine manuell gelabelte Ground-Truth über den ganzen Run).</p>
</div>
</div>
"""
