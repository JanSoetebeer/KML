# Abschlussauswertung Modulhandbuch-Crawler

Stand: 06.10.2026 (endgültig) · Datenbasis: alle Läufe (August-Lauf, Deep Run, Seeds-Läufe), OCR-Nachbearbeitung, zwei LLM-Review-Stufen mit Claude Haiku 4.5 auf Amazon Bedrock.
Alle Zahlen stammen aus `auswertung/data/kennzahlen.json` und lassen sich mit den Skripten in Abschnitt 8 neu erzeugen. Die 24 Grafiken liegen in `auswertung/charts/`.

---

## 1. Kurzfazit

1. **Der Crawl im großen Maßstab hat funktioniert.** 164.396 verschiedene PDFs von mehr als 1.000 Hosts (404 Hochschulen der Hochschulliste) wurden geladen. Der Deep Run holte allein 132.187 PDFs in rund 13 Stunden.
2. **Der TF-IDF-Klassifikator allein reicht für das Ziel „nur Modulhandbücher“ nicht.** Im Training lag die Precision bei 96,5 %, im echten Crawl nur bei 25 % (Score 0,5–0,9) bzw. 82,5 % (Score ≥ 0,9). Grund sind viele Beinahe-Treffer: Prüfungsordnungen, Einzel-Modulblätter, Studienverlaufspläne.
3. **Die LLM-Zweitstufe hat die Qualität stark verbessert.** 34.141 Dokumente wurden vom LLM geprüft, 11.771 davon bestätigt, 22.367 verworfen. Gesichert (LLM-bestätigt) sind **11.771 Modulhandbücher**. Dazu kommen **7.278 Dokumente mit Score ≥ 0,9, die nicht LLM-geprüft sind**. Nach der Stichprobe sind davon etwa 94 % echt (≈ 6.900). Geschätzt echt insgesamt: **≈ 18.600** (Bereich 18.350–18.800) bei 19.049 gelisteten Dokumenten.
4. **Ein Host-Effekt war entscheidend.** Auf 197 „verdächtigen“ Hosts (LLM bestätigt dort sonst unter 30 %) waren selbst Dokumente mit Score ≥ 0,9 nur zu 68 % echt, auf den übrigen Hosts zu 94 %. Das gezielte Nachprüfen dieser 6.463 Dokumente hat die Precision der Endliste von ca. 89 % auf ca. 98 % angehoben.
5. **Abdeckung:** 255 von 404 Hochschulen (63 %) haben mindestens ein bestätigtes Modulhandbuch, 263 (65 %) inklusive der ungeprüften. 39 Hochschulen blieben ohne jedes Ergebnis.
6. **Das LLM ist keine fehlerfreie Referenz.** Eine manuelle Stichprobe von 20 Dokumenten ergab 17 Übereinstimmungen (85 %): ein falsch bestätigtes und zwei falsch verworfene Dokumente. Alle Precision-Angaben messen die Übereinstimmung mit dem LLM, nicht mit einer menschlichen Wahrheit.

---

## 2. Datenbasis und Methode

| Lauf | Datum | PDFs (URL-eindeutig) | Hosts | Rolle |
|---|---|---|---|---|
| August-Lauf (`run_full`) | 12.08.2026 | 65.773 | 743 | erster Bulk-Crawl, 411 Hochschulen, ca. 6,3 h |
| Deep Run (`deep_run`) | 16.–17.09.2026 | 132.187 | 1.165 | Basis der Auswertung |
| Seeds-Läufe | 03.–16.09.2026 | 431 / 135 / 215 | – | gezielte Nachsuche; nur 345 Dokumente (Seeds-only-Lauf) waren in keinem anderen Lauf enthalten |

- **Basis = Deep Run.** Dokumente, die nur der August-Lauf fand (31.890 URLs auf 296 nur dort gefundenen Hosts), werden mitgeführt und gesondert gekennzeichnet. Bei Überlappung (33.883 URLs) gilt der Deep Run. Gesamt: **164.396** Dokumente.
- **Zweitstufe.** LLM-Urteile werden per URL auf die Dokumentzeile gelegt. Das LLM-Urteil ist maßgeblich (`llm_confirmed` nur bei Konfidenz ≥ 0,8; praktisch alle Urteile liegen bei 0,8–1,0).
- **Definition „Modulhandbuch“** (System-Prompt des LLM): systematisches Handbuch, das die Module eines Studiengangs beschreibt. Einzelne Modulblätter, Prüfungsordnungen, Studienverlaufspläne und Vorlesungsverzeichnisse zählen nicht. Das Modell sieht nur die ersten 8.000 Zeichen eines Dokuments.
- **Status je Dokument** (`tier` in `auswertung/data/final.jsonl`):

| Status | Dokumente |
|---|---|
| LLM bestätigt | 11.771 |
| TF-IDF ≥ 0,9, nicht LLM-geprüft | 7.278 |
| Positiv aus anderem Lauf (August/Seeds), nicht LLM-geprüft | 6.393 |
| LLM verworfen | 22.367 |
| TF-IDF negativ, nicht LLM-geprüft | 114.926 |
| ungeklärt (kein Text, Fehler) | 1.658 |
| LLM unsicher | 3 |

Dazu die Grafiken 01 und 02.

---

## 3. Zentrale Zahlen

### Endliste
| Variante | Dokumente | Eindeutig (Host + Dateiname) |
|---|---|---|
| streng (nur LLM-bestätigt) | 11.771 | 10.165 |
| erweitert (inkl. TF-IDF ≥ 0,9, ungeprüft) | 19.049 | 16.316 |

Geschätzt echte Modulhandbücher in der erweiterten Liste: ≈ 18.600 von 19.049, das entspricht einer Precision von ≈ 98 % **gemessen am LLM-Urteil**. Grundlage: Stichprobe auf den nicht verdächtigen Hosts, 212 von 225 bestätigt (94,2 %, 95-%-Intervall 90,4–96,6 %).

### Abdeckung (404 Hochschulen)
| | streng | erweitert |
|---|---|---|
| Hochschulen mit ≥ 1 Modulhandbuch | 255 (63 %) | 263 (65 %) |
| Hochschulen mit ≥ 10 Modulhandbüchern | 138 | 158 |
| Hochschulen ohne Ergebnis (nichts gefunden) | 39 | 39 |

- Median: 4 Modulhandbücher pro Hochschule. Die 10 ergiebigsten Hochschulen liefern 40 % aller Ergebnisse (Grafiken 10, 17).
- Nach Typ (erweitert): Universitäten 76 % abgedeckt (91/120), Fachhochschulen/HAW 60 % (117/194), Künstlerische Hochschulen 70 % (39/56), Verwaltungshochschulen 44 % (12/27). Grafik 11.
- Nach Träger: öffentlich-rechtlich 201/258 (78 %), privat 42/108 (39 %), kirchlich 19/37 (51 %). Grafik 12.
- Status der Hochschulen (Grafik 15): Vor der Bereinigung 293 „ok“ (≥ 3 Handbücher), danach 211 (streng) bzw. 219 (erweitert). Die Zahl der Hochschulen mit Dokumenten, aber ohne Handbuch stieg von 44 auf 102–110, weil falsche Positive entfielen.
- Zielgröße „≈ 40.000“ (Fachschätzung, Referenz für Recall): erreicht ca. 40 % (16.316 eindeutige gelistete Dokumente, davon geschätzt ≈ 16.000 echt). Das ist eine Größenordnung, keine Messung.

### LLM-Review (Grafik 05)
| Lauf | geprüft | bestätigt |
|---|---|---|
| Review-Band des August-Laufs (Score 0,3–0,7) | 6.065 | 1.845 (30 %) |
| Positive 0,5–0,9 des Deep Runs | 20.966 | 5.153 (25 %) |
| Pilot: Stichprobe Positive ≥ 0,9 | 400 | 330 (82,5 %) |
| OCR-Treffer (Score ≥ 0,5) | 247 | 42 (17 %) |
| Positive ≥ 0,9 auf verdächtigen Hosts | 6.463 | 4.404 (68 %) |

Aufwand (Schätzung ohne Abrechnung): ≈ 34.100 Dokumente mit je ≈ 2.300 Eingabe-Token, grob 85–100 $ bei Haiku-4.5-Preisen. Das Tageslimit von Bedrock begrenzte den Durchsatz.

### Precision je Score-Bereich (Grafik 03)
| Score | Bestätigungsrate | n |
|---|---|---|
| 0,5–0,6 | 8 % | 5.753 |
| 0,6–0,7 | 13 % | 4.463 |
| 0,7–0,8 | 30 % | 4.444 |
| 0,8–0,9 | 44 % | 6.306 |
| ≥ 0,9 | 82,5 % | 400 (Pilot) |

Der Score ist deutlich weniger „sicher“, als die Trainingsmetrik nahelegt (Grafik 23). Selbst innerhalb einer Score-Klasse hängt die Qualität stark vom Host ab (Grafik 24: 68 % auf verdächtigen, 94 % auf übrigen Hosts bei Score ≥ 0,9).

### Fehlerarten des Klassifikators (Grafik 07)
20.031 TF-IDF-Positive wurden vom LLM verworfen:

| Art | Dokumente | Anteil |
|---|---|---|
| Prüfungs-/Studienordnung, Satzung | 9.919 | 50 % |
| Einzelnes Modul / Datenblatt / Syllabus | 4.107 | 21 % |
| Studienverlaufs-/Studienplan | 2.080 | 10 % |
| Sonstiges (nicht zuordenbar) | 1.827 | 9 % |
| Modul-/Wahlpflichtkatalog (unvollständig) | 933 | 5 % |
| Vorlesungs-/Veranstaltungsverzeichnis | 737 | 4 % |
| Antrag, Formular, Merkblatt, Flyer | 428 | 2 % |

Zuordnung per Stichwort aus der LLM-Begründung, daher grob.

### Weitere Befunde
- **Dateiname als Signal (Grafik 08):** Enthält der Dateiname „modul“, „handbuch“ oder „mhb“, wird bei Score ≥ 0,9 in 95 % der Fälle bestätigt (n = 4.399), ohne Stichwort in 35 % (n = 3.529). Bei Score 0,5–0,7 sind es 36 % gegen 8 %.
- **OCR (Grafik 09):** 3.619 gescannte PDFs, 3.553 bearbeitet, 3.118 mit Text, nur 247 mit Score ≥ 0,5, davon 42 bestätigt. Aufwand hoch, Ertrag klein (≈ 1 % der Ausgangsmenge).
- **Duplikate (Grafik 22):** 2.733 Einträge der erweiterten Liste sind Duplikate (gleicher Host und Dateiname), bei der strengen Liste 1.606.
- **Aktualität (Grafik 19):** Bei 11.758 von 19.049 Dokumenten steht eine Jahreszahl im Dateinamen, Schwerpunkt 2020–2026.
- **Durchsatz (Grafik 18):** 10.000–14.000 neue PDFs pro Stunde im Spitzenbereich.
- **Manuelle Gegenprobe (20 Dokumente):** 8 von 8 ungeprüften TF-IDF-Positiven ≥ 0,9 echt; 5 von 6 LLM-bestätigten richtig; 4 von 6 LLM-verworfenen richtig. Die zwei falsch verworfenen waren laut LLM-Begründung „Studienordnung“, vermutlich weil nur der Textanfang gesehen wird (Vermutung, nicht geprüft). Mit n = 20 ist das Intervall breit (etwa 64–95 % Übereinstimmung).

---

## 4. Was hat im Projekt geklappt

- **Skalierung.** Der Crawler verarbeitete über 160.000 PDFs von Hunderten Hochschulen in wenigen Stunden pro Lauf (Fargate-Batch), mit Domain-Scope und Politeness.
- **Zweistufige Klassifikation.** Schnelles, günstiges TF-IDF-Modell für den Massenfilter, LLM für die Grauzone. Das wirkte gezielt: 70–75 % der unsicheren Positiven wurden aussortiert, ohne 160.000 Dokumente an ein LLM zu schicken.
- **Gezielte Nachprüfung statt Vollprüfung.** Die Host-Analyse fand die Stellen mit den meisten Fehlern. So stieg die Precision der Endliste deutlich, ohne alle 13.700 ungeprüften Dokumente zu prüfen.
- **Modulare Architektur.** Extraktionsprofile, spezifikationsgesteuerter LLM-Review (`specs.py`), Discovery (Common Crawl, Serper) und OCR-Fallback sind für andere Dokumenttypen wiederverwendbar.
- **Discovery-Wirkung.** In einem Test auf drei Hochschulen mit 0 Treffern im ersten Lauf fanden Serper und Common Crawl gezielt 13 Modulhandbücher.
- **Auswertungswerkzeuge.** Eigenes Evaluationsmodul mit Diagnose je Hochschule, Szenarien nach Typ/Träger/Größe/Bundesland und Re-Scoring ohne neuen Crawl.
- **Betrieb.** CI/CD per GitHub Actions, reproduzierbarer AWS-Aufbau (Bootstrap-Skript), Webapp für Human-in-the-Loop.
- **Transparenz.** Jede Entscheidung ist mit Score, Quelle, Lauf und (bei LLM) Begründung gespeichert.

## 5. Was hat nicht (oder nur teilweise) geklappt

- **Übertragung der Trainingsgüte auf die Praxis.** CV-Precision 96,5 % gegen 25 % bzw. 82,5 % im echten Crawl. Das Trainingsset (2.695 Dokumente von 269 Hochschulen) bildet die Breite der Beinahe-Treffer im Web nicht ab. Außerdem war die Schwelle im Deep Run mit 0,5 niedrig (das aktuelle Modell schlägt 0,8 vor) und erzeugte die Positiv-Flut (37.993 Positive im Deep Run).
- **Recall bleibt unvollständig.** Etwa 60 % der erwarteten Handbücher wurden nicht gefunden. 39 Hochschulen ohne Ergebnis, 110 mit Dokumenten, aber ohne bestätigtes Handbuch (streng). Besonders private (39 %) und Verwaltungshochschulen (44 %) sind schlecht abgedeckt: kleine Seiten, Login-Bereiche, JavaScript-Portale, kaum PDFs.
- **Nicht jedes Ergebnis ist LLM-geprüft.** 7.278 Positive (≥ 0,9, nicht verdächtige Hosts) und 6.393 Positive aus anderen Läufen sind ungeprüft. Letztere sind weder in der strengen noch in der erweiterten Liste.
- **OCR.** Hoher Aufwand (Tesseract lokal, über 3.500 Dokumente), nur 42 zusätzliche bestätigte Treffer.
- **Definition.** Ob einzelne Modulblätter, Studienverlaufspläne und Modulkataloge zählen, ist Auslegungssache. Das LLM wendet eine strenge Definition an (Grafik 07: 21 % der Fehler sind Einzelblätter).
- **Das LLM macht Fehler in beide Richtungen.** In der Stichprobe wurden zwei echte Handbücher verworfen (Studienordnung mit Modulbeschreibungen, nur der Textanfang war sichtbar) und ein Dokument mit Score 0,37 fälschlich bestätigt. Die Zahl der verpassten Handbücher ist damit höher, als die Tabellen zeigen.
- **Betriebsreibung.** Bedrock-Tageslimit, kurzlebige Keys, die nur in ihrer Ausstellungsregion gelten, ablaufende AWS-Zugangsdaten, TLS-Interception im Firmennetz, Sandbox-Lease. Das verlangsamte die Bereinigung, veränderte sie aber nicht.
- **Grobe Recall-Schätzung.** Bei den 18.252 Negativen mit Score 0,3–0,5 sind es nach einer kleinen, nicht repräsentativen Stichprobe ca. 380 verpasste Handbücher. Das ist sehr unsicher. Die alte August-Stichprobe, die 22–32 % ergab, stammt vom älteren Modell und gilt für die neuen Scores nicht.

## 6. Empfehlungen und Ausblick

1. **Bericht:** beide Listen nennen. „Streng“ (11.771) für Qualitätsaussagen, „erweitert“ (19.049 gelistet, ≈ 18.600 echt) für Mengenaussagen. Die Precision stets mit dem Zusatz „gemessen am LLM-Urteil“ angeben.
2. **Manuelle Stichprobe vervollständigen:** 100 der 120 vorbereiteten Dokumente sind noch offen (`stichprobe_manuelle_pruefung.csv`). Das ist die einzige echte Genauigkeitsmessung des LLM.
3. **Verbesserungen für ein nächstes Projekt:** höhere Schwelle (≥ 0,8) im Live-Crawl, Dateiname und Host als Features, Nachtraining mit den über 34.000 LLM-Labels (viele schwierige Negative), mehr Textumfang für Dokumente, die mit einer Ordnung beginnen, Seitenebene statt Dateiebene für JS-Portale.
4. **Optional, mit Restbudget:** die 7.278 ungeprüften Dokumente (≈ 18 $) und die 6.393 Positiven aus dem August-Lauf (≈ 16 $) durch das LLM schicken.

---

## 7. Abbildungsverzeichnis (Vorschlag für den Bericht)

| Nr. | Datei | Zeigt | Passt zu Kapitel |
|---|---|---|---|
| 01 | `01_trichter.png` | Vom Crawl (164.396 PDFs) über TF-IDF-Positive (44.437) zu LLM-bestätigten (11.771) und geschätzt echten (≈ 18.600) | Ergebnisse / Überblick |
| 02 | `02_endstatus_nach_quelle.png` | Endstatus aller Dokumente nach Lauf | Datenbasis |
| 03 | `03_precision_je_score.png` | LLM-Bestätigungsrate je TF-IDF-Score (8 % … 82,5 %) | Klassifikator / Evaluation |
| 04 | `04_score_histogramm.png` | Score-Verteilung nach Endstatus (log) | Klassifikator |
| 05 | `05_llm_laeufe.png` | LLM-Läufe, Umfang und Bestätigungsrate | LLM-Zweitstufe |
| 06 | `06_llm_konfidenz.png` | Konfidenzverteilung der LLM-Urteile | LLM-Zweitstufe |
| 07 | `07_fehlerarten.png` | Typen falscher Positive (Ordnungen, Einzelmodule …) | Fehleranalyse |
| 08 | `08_dateiname_signal.png` | Dateiname als Zusatzsignal | Fehleranalyse / Ausblick |
| 09 | `09_ocr_trichter.png` | OCR-Ertrag | Grenzen |
| 10 | `10_mh_pro_hochschule.png` | Verteilung der Treffer pro Hochschule | Abdeckung |
| 11 | `11_abdeckung_typ.png` | Abdeckung nach Hochschultyp | Abdeckung |
| 12 | `12_abdeckung_traeger.png` | Abdeckung nach Trägerschaft | Abdeckung |
| 13 | `13_abdeckung_groesse.png` | Abdeckung nach Größe | Abdeckung |
| 14 | `14_abdeckung_bundesland.png` | Abdeckung nach Bundesland | Abdeckung |
| 15 | `15_hochschul_status.png` | Hochschul-Status vor und nach der Bereinigung | Abdeckung |
| 16 | `16_groesse_vs_ausbeute.png` | Studierendenzahl gegen Treffer pro Hochschule | Abdeckung |
| 17 | `17_top_hosts.png` | Die 20 ergiebigsten Hosts | Abdeckung |
| 18 | `18_durchsatz.png` | Crawl-Durchsatz je Lauf | Crawler / Betrieb |
| 19 | `19_jahre_im_dateinamen.png` | Aktualität der Handbücher | Ergebnisse |
| 20 | `20_laeufe_vergleich.png` | Überlappung August-Lauf und Deep Run | Crawler |
| 21 | `21_recall_luecke.png` | Was wir haben und was fehlen könnte (grobe Schätzung) | Grenzen |
| 22 | `22_duplikate.png` | Duplikate in der Endliste | Datenqualität |
| 23 | `23_training_vs_praxis.png` | Precision: Training vs. echter Crawl | Klassifikator (Kernaussage) |
| 24 | `24_hosts_precision.png` | Precision auf verdächtigen vs. übrigen Hosts (68 % vs. 94 %) | Fehleranalyse |

Farben: festes Schema über alle Grafiken (blau = LLM-bestätigt, grün = TF-IDF ≥ 0,9 ungeprüft, orange = verworfen, grau = negativ). PNG, 200 dpi.

## 8. Dateien und Reproduzierbarkeit

| Datei | Inhalt |
|---|---|
| `auswertung/build_final.py` | baut `data/final.jsonl` aus allen Läufen, OCR- und LLM-Ergebnissen |
| `auswertung/build_eval_manifests.py` | erzeugt die Manifeste `eval_strict.jsonl` / `eval_likely.jsonl` |
| `auswertung/make_charts.py` | erzeugt alle Grafiken, `data/kennzahlen.json` und die Stichprobe |
| `auswertung/data/per_uni_strict.csv`, `per_uni_likely.csv` | Diagnose je Hochschule (Flag, Anzahl, Aktion) |
| `auswertung/data/eval_strict.html`, `eval_likely.html` | vollständiger Evaluationsbericht je Variante |
| `auswertung/hosts_verdaechtig.csv` | Hosts mit ungeprüften Positiven und LLM-Bestätigungsrate |
| `auswertung/stichprobe_manuelle_pruefung.csv` | 120 Dokumente für die manuelle Prüfung |

Neu erzeugen, aus dem Repo-Root:

```
python auswertung/build_final.py
python auswertung/build_eval_manifests.py
cd webscraper
python -m webscraper.evaluation --manifest ../auswertung/data/eval_strict.jsonl --csv "../hs_liste_ready_for_import 1.csv" --expected-total 40000 --run-id final-strict --out-html ../auswertung/data/eval_strict.html --out-json ../auswertung/data/eval_strict.json --out-per-uni ../auswertung/data/per_uni_strict.csv
python -m webscraper.evaluation --manifest ../auswertung/data/eval_likely.jsonl --csv "../hs_liste_ready_for_import 1.csv" --expected-total 40000 --run-id final-likely --out-html ../auswertung/data/eval_likely.html --out-json ../auswertung/data/eval_likely.json --out-per-uni ../auswertung/data/per_uni_likely.csv
cd ..
.venv\Scripts\python auswertung\make_charts.py
```
