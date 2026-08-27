# Crawl-Run Evaluation

Bewertet einen Bulk-Crawl-Lauf des Modulhandbuch-Scrapers: verknüpft das
**Review-Manifest** (die Klassifikations-Ergebnisse pro Dokument) mit der
**Hochschul-Liste** (Seed-CSV) und erzeugt einen **HTML-Report** plus einen
maschinenlesbaren **JSON-Dump** nach einheitlichem Datenschema.

Reines Python (Standardbibliothek) — läuft überall, wo der Scraper läuft.

## Datenquellen

| Quelle | Was | Woher |
|---|---|---|
| Manifest `*.jsonl` | eine Zeile je geladenem PDF: Score, `decision`, `is_module_handbook`, Hostname, Timestamp | `s3://<bucket>/manifests/<batch_id>.jsonl` (von der `ClassificationPipeline` hochgeladen) |
| Hochschul-CSV | Seed-Liste: Name, Typ, Träger, Bundesland, Studierende, URL | `hs_liste_ready_for_import 1.csv` |

**Join-Schlüssel** ist die *registrierte Domain* (letzte zwei DNS-Labels), weil
der Crawler domain-gebunden ist — jedes Dokument einer Hochschule stammt von
deren eigener Domain (inkl. Subdomains, z. B. `www-docs.b-tu.de` → `b-tu.de`).

## Verwendung

Manifest aus S3 laden (Windows/PowerShell, Bucket ggf. anpassen):

```bash
aws s3 cp s3://webscraper-output-081757578883/manifests/<BATCH_ID>.jsonl run_full.jsonl
```

Report erzeugen (aus dem Verzeichnis `webscraper/`):

```bash
python -m webscraper.evaluation \
  --manifest run_full.jsonl \
  --csv "../hs_liste_ready_for_import 1.csv" \
  --expected-total 40000 \
  --run-id "bulk-411-2026-08-12" \
  --out-html evaluation_report.html \
  --out-json evaluation_data.json
```

Mehrere Manifeste (z. B. mehrere Shards eines Laufs) einfach hintereinander an
`--manifest` hängen.

## Datenschema (`schema.py`)

Ein `MetricSet` wird **für jedes Szenario identisch** berechnet — dadurch sind
alle Zahlen direkt vergleichbar.

- `DocumentRecord` — ein geladenes Dokument (eine Manifest-Zeile).
- `UniversityResult` — Stammdaten + alle Dokumente einer Hochschule + abgeleitete Metriken.
- `MetricSet` — der vergleichbare Metrik-Bund (Coverage, Positiv-Quote, MH/Uni …).
- `ScenarioResult` — benanntes Szenario (Segment **oder** Einzelhochschule) inkl. optionalem `Expectation`-Check (PASS/FAIL).
- `TemporalAnalysis`, `ThroughputAnalysis`, `RunEvaluation` — Zeit, Tempo, Gesamtcontainer.

### Geprüfte Szenarien

- **Global** — alle Hochschulen.
- **Segmente** (gleiche Metriken, gruppiert): Träger (öffentlich / privat / kirchlich),
  Hochschultyp (Uni / FH-HAW / Künstlerisch / Verwaltung), Größenklasse
  (Studierende), Bundesland.
- **Deep Dives** (Einzelhochschulen mit Erwartung): FernUni Hagen (größte, Fernstudium),
  NORDAKADEMIE (Erwartung ≈ 0 → deckt False Positives auf), Evangelische Hochschule
  Berlin (kleine kirchliche HS), FH Wedel (Referenz „einige, aber nicht alle").

Deep-Dive-Hochschulen und Erwartungen werden in `evaluate.DEEP_DIVES` gepflegt.

## Report-Abschnitte

1. Gesamtergebnis & Klassifikation (positiv / review / negativ)
2. Szenario-Vergleich (einheitliche Metriken) + Coverage nach Träger/Typ
3. Deep Dives inkl. Erwartungsabgleich
4. Verteilung „ein paar bei vielen" (MH pro Hochschule) + Top-15
5. Lückenanalyse: A) gecrawlt aber 0 MH · B) keine Dokumente gefunden
6. Zeitliche Analyse (Jahrgänge aus Dateinamen) + Crawl-Verlauf
7. Geschwindigkeit & Hochrechnung für künftige Runs

## Hinweise / Grenzen

- **Durchsatz** wird aus Dokument-Zeitstempeln gemessen (Dokumente/Sekunde), nicht
  aus rohen HTTP-Requests. Echte *pages/second* stünden nur in den Scrapy-Stats
  (CloudWatch-Log des Fargate-Tasks).
- **„~40k erwartet"** ist eine Domänen-Schätzung real existierender Modulhandbücher
  und dient nur als Recall-Referenz. Das Review-Band ist potenzieller Zusatz-Recall.
- **Positiv-Quote ≠ Präzision** im ML-Sinn — es gibt keine manuell gelabelte
  Ground-Truth über den ganzen Lauf.
