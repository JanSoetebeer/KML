# Abschlussauswertung Modulhandbuch-Crawler

Stand: 02.10.2026 · Datenbasis: alle Läufe (August-Lauf, Deep Run, Seeds-Läufe), OCR-Nachbearbeitung, LLM-Review mit Claude Haiku 4.5 auf Amazon Bedrock.
Alle Zahlen stammen aus `auswertung/data/kennzahlen.json` und lassen sich mit den Skripten unten neu erzeugen. Die 23 Grafiken liegen in `auswertung/charts/`.

---

## 1. Kurzfazit

1. **Crawl im großen Maßstab hat funktioniert.** 164.396 verschiedene PDFs von 1.000+ Hosts (404 Hochschulen der Hochschulliste) wurden heruntergeladen. Der Deep Run holte 132.187 PDFs in rund 13 Stunden.
2. **Der TF-IDF-Klassifikator allein reicht für das Ziel „nur Modulhandbücher“ nicht.** Im Training lag die Precision bei 96,5 %, im echten Crawl nur bei 82,5 % (Score ≥ 0,9) bzw. 25 % (Score 0,5–0,9). Der Grund sind sehr viele Beinahe-Treffer (Prüfungsordnungen, Einzel-Modulblätter, Studienverlaufspläne).
3. **Die LLM-Zweitstufe hat die Qualität stark verbessert.** 27.678 Dokumente wurden vom LLM geprüft. 7.367 davon bestätigt, 20.308 verworfen. Gesichert (LLM-bestätigt) sind **7.367 Modulhandbücher**. Hinzu kommen **13.741 Dokumente mit Score ≥ 0,9, die nicht LLM-geprüft sind**, von denen nach dem Pilot grob 82,5 % echt sind (≈ 11.300). Geschätzt echt insgesamt: **≈ 18.700** (Bereich 18.150–19.170).
4. **Abdeckung:** 248 von 404 Hochschulen (61 %) haben mindestens ein bestätigtes Modulhandbuch, 263 (65 %) inklusive der ungeprüften Hochschulen. 39 Hochschulen blieben ohne jedes Ergebnis.
5. **Die Referenz ist das LLM, nicht ein Mensch.** Eine manuelle Stichprobe (120 Dokumente, `stichprobe_manuelle_pruefung.csv`) ist vorbereitet, aber noch nicht ausgewertet.

---

## 2. Datenbasis und Methode

| Lauf | Datum | PDFs (URL-eindeutig) | Hosts | Rolle |
|---|---|---|---|---|
| August-Lauf (`run_full`) | 12.08.2026 | 65.773 | 743 | erster Bulk-Crawl, 411 Hochschulen, ca. 6,3 h |
| Deep Run (`deep_run`) | 16.–17.09.2026 | 132.187 | 1.165 | Basis der Auswertung |
| Seeds-Läufe | 03.–16.09.2026 | 431 / 135 / 215 | – | gezielte Nachsuche; nur 345 Dokumente (Seeds-only-Lauf) waren in keinem anderen Lauf enthalten |

- **Basis = Deep Run.** Dokumente, die nur der August-Lauf fand (31.890 URLs, 296 Hosts nur dort), werden mitgeführt, aber gesondert gekennzeichnet. Bei Überlappung (33.883 URLs) gilt der Deep Run. Gesamt: **164.396** Dokumente.
- **Zweitstufe.** Frühere LLM-Urteile werden per URL auf die Deep-Run-Zeile gelegt. Das LLM-Urteil ist maßgeblich (`llm_confirmed` nur bei Konfidenz ≥ 0,8; praktisch alle Urteile liegen bei 0,8–1,0).
- **Definition „Modulhandbuch“** (System-Prompt des LLM): systematisches Handbuch, das die Module eines Studiengangs beschreibt. Einzelne Modulblätter, Prüfungsordnungen, Studienverlaufspläne und Vorlesungsverzeichnisse zählen nicht.
- **Status je Dokument** (`tier` in `auswertung/data/final.jsonl`):

| Status | Dokumente |
|---|---|
| LLM bestätigt | 7.367 |
| TF-IDF ≥ 0,9, nicht LLM-geprüft | 13.741 |
| Positiv aus anderem Lauf, nicht LLM-geprüft | 6.393 |
| LLM verworfen | 20.308 |
| TF-IDF negativ, nicht LLM-geprüft | 114.926 |
| ungeklärt (kein Text, Fehler) | 1.658 |
| LLM unsicher | 3 |

Dazu die Grafiken 01 und 02.

---

## 3. Zentrale Zahlen

### Endliste
| Variante | Dokumente | Eindeutig (Host + Dateiname) |
|---|---|---|
| streng (nur LLM-bestätigt) | 7.367 | 5.947 |
| inkl. TF-IDF ≥ 0,9 (ungeprüft) | 21.108 | 18.268 |

Geschätzt echte Modulhandbücher in der erweiterten Liste: ≈ 18.700 von 21.108 gelisteten, das entspricht einer **Precision von ≈ 89 %** (aus der Pilot-Stichprobe: 330 von 400 bestätigt, 95-%-Intervall 78,5–85,9 % für die ungeprüfte Gruppe).

### Abdeckung (404 Hochschulen)
| | streng | inkl. ≥ 0,9 |
|---|---|---|
| Hochschulen mit ≥ 1 Modulhandbuch | 248 (61 %) | 263 (65 %) |
| Hochschulen mit ≥ 10 Modulhandbüchern | 110 | 161 |
| Hochschulen ohne Ergebnis (nichts gefunden) | 39 | 39 |

- Median: 4 Modulhandbücher pro Hochschule (erweiterte Liste). Die 10 ergiebigsten Hochschulen liefern 37 % aller Ergebnisse (Grafik 10, 17).
- Nach Typ: Universitäten 76 % abgedeckt (91/120), Fachhochschulen/HAW 60 % (117/194), Künstlerische Hochschulen 70 % (39/56), Verwaltungshochschulen 44 % (12/27). Grafik 11.
- Nach Träger: öffentlich-rechtlich 201/258 (78 %), privat 42/108 (39 %), kirchlich 19/37 (51 %). Grafik 12.
- Zielgröße „≈ 40.000“ (Fachschätzung, Referenz für Recall): erreicht ca. 40–46 % (18.268 eindeutige gelistete Dokumente, davon geschätzt ≈ 16.200 echt), eine grobe Größenordnung, keine Messung.

### LLM-Review
| Lauf | geprüft | bestätigt |
|---|---|---|
| Review-Band des August-Laufs (Score 0,3–0,7) | 6.065 | 1.845 (30 %) |
| Positive 0,5–0,9 des Deep Runs | 20.966 | 5.153 (25 %) |
| Pilot: Stichprobe Positive ≥ 0,9 | 400 | 330 (82,5 %) |
| OCR-Treffer (Score ≥ 0,5) | 247 | 42 (17 %) |

Aufwand (Schätzung ohne Abrechnung): ca. 27.700 Dokumente à ≈ 2.300 Token Eingabe, grob 70–80 $ bei Haiku-4.5-Preisen. Das Tageslimit von Bedrock begrenzte den Durchsatz.

### Precision je Score-Bereich (Grafik 03)
| Score | Bestätigungsrate | n |
|---|---|---|
| 0,5–0,6 | 8 % | 5.753 |
| 0,6–0,7 | 13 % | 4.463 |
| 0,7–0,8 | 30 % | 4.444 |
| 0,8–0,9 | 44 % | 6.306 |
| ≥ 0,9 | 82,5 % | 400 (Pilot) |

Der Score ist also deutlich weniger „sicher“, als die Trainingsmetrik nahelegt (Grafik 23).

### Fehlerarten des Klassifikators (Grafik 07)
17.972 TF-IDF-Positive wurden vom LLM verworfen:

| Art | Dokumente | Anteil |
|---|---|---|
| Prüfungs-/Studienordnung, Satzung | 8.626 | 48 % |
| Einzelnes Modul / Datenblatt / Syllabus | 3.434 | 19 % |
| Studienverlaufs-/Studienplan | 2.076 | 12 % |
| Sonstiges (nicht zuordenbar) | 1.755 | 10 % |
| Modul-/Wahlpflichtkatalog (unvollständig) | 925 | 5 % |
| Vorlesungs-/Veranstaltungsverzeichnis | 730 | 4 % |
| Antrag, Formular, Merkblatt, Flyer | 426 | 2 % |

Zuordnung per Stichwort aus der LLM-Begründung, daher grob.

### Weitere Befunde
- **Dateiname als Signal (Grafik 08):** Enthält der Dateiname „modul“, „handbuch“ oder „mhb“, wird bei Score ≥ 0,9 in 90 % der Fälle bestätigt, ohne Stichwort nur in 41 %. Bei Score 0,5–0,7 sind es 36 % gegen 8 %.
- **OCR (Grafik 09):** 3.619 gescannte PDFs, 3.553 per OCR bearbeitet, 3.118 mit Text, nur 247 mit Score ≥ 0,5, davon 42 bestätigt. Aufwand hoch, Ertrag klein (≈ 1 % der Ausgangsmenge).
- **Duplikate (Grafik 22):** In der erweiterten Liste sind 2.840 Einträge Duplikate (gleicher Host und Dateiname), in der strengen 1.420.
- **Aktualität (Grafik 19):** Bei 12.963 von 21.108 Dokumenten steht eine Jahreszahl im Dateinamen. Verteilung von 2005 bis 2027, Schwerpunkt 2020–2026.
- **Durchsatz (Grafik 18):** 10.000–14.000 neue PDFs pro Stunde im Spitzenbereich.

---

## 4. Was hat im Projekt geklappt

- **Skalierung.** Der Crawler verarbeitete über 160.000 PDFs von Hunderten Hochschulen in wenigen Stunden pro Lauf (Fargate-Batch), mit Domain-Scope und Politeness.
- **Zweistufige Klassifikation.** Schnelles, günstiges TF-IDF-Modell für den Massenfilter, LLM nur für die Grauzone. Das hat gezielt gewirkt: 70–75 % der unsicheren Positiven wurden aussortiert, ohne 160.000 Dokumente an ein LLM zu schicken.
- **Modulare Architektur.** Extraktionsprofile, spezifikationsgesteuerter LLM-Review (`specs.py`), Discovery (Common Crawl, Serper) und OCR-Fallback sind wiederverwendbar für andere Dokumenttypen.
- **Discovery-Wirkung.** In einem Test auf drei Hochschulen, die im ersten Lauf 0 Treffer hatten, fanden Serper und Common Crawl gezielt 13 Modulhandbücher.
- **Auswertungswerkzeuge.** Eigenes Evaluationsmodul mit Per-Hochschule-Diagnose, Szenarien nach Typ/Träger/Größe/Bundesland, Re-Scoring ohne neuen Crawl.
- **Betrieb.** CI/CD per GitHub Actions, reproduzierbarer AWS-Aufbau (Bootstrap-Skript), Webapp für Human-in-the-Loop.
- **Transparenz.** Jede Entscheidung ist mit Score, Quelle, Lauf und (bei LLM) Begründung nachvollziehbar gespeichert.

## 5. Was hat nicht (oder nur teilweise) geklappt

- **Übertragung der Trainingsgüte auf die Praxis.** CV-Precision 96,5 % vs. 82,5 % bzw. 25 % im echten Crawl. Das Trainingsset (2.695 Dokumente, 269 Hochschulen) bildet die Breite der Beinahe-Treffer im Web nicht ab. Außerdem war die Schwelle im Deep Run mit 0,5 sehr niedrig (das aktuelle Modell schlägt 0,8 vor), das erzeugte die Positiv-Flut (37.993 Positive im Deep Run).
- **Recall bleibt unvollständig.** Etwa die Hälfte der erwarteten Handbücher wurde nicht gefunden. 39 Hochschulen ohne Ergebnis, 117 mit Dokumenten, aber ohne bestätigtes Modulhandbuch (streng). Besonders private (39 %) und Verwaltungshochschulen (44 %) sind schlecht abgedeckt: kleine Seiten, Login-Bereiche, JavaScript-Portale, kaum PDFs.
- **Nicht jedes Ergebnis ist LLM-geprüft.** 13.741 Positive (≥ 0,9) und 6.393 Positive aus anderen Läufen sind ungeprüft. Auf 159 Hosts, die zusammen 6.464 dieser ungeprüften Dokumente halten, hat das LLM bei seinen anderen Prüfungen unter 30 % bestätigt (`hosts_verdaechtig.csv`, z. B. uni-hamburg.de, uni-flensburg.de, tu-braunschweig.de). Dort liegt vermutlich der größte Anteil der verbleibenden Fehler.
- **OCR.** Hoher Aufwand (Tesseract lokal, über 3.500 Dokumente), nur 42 zusätzliche bestätigte Treffer.
- **Definition.** Ob einzelne Modulblätter, Studienverlaufspläne und Modulkataloge zählen, ist Auslegungssache. Das LLM wendet eine strenge Definition an (Grafik 07: 19 % der Fehler sind Einzelblätter).
- **Betriebsreibung.** Bedrock-Tageslimit, ablaufende Zugangsdaten (ca. alle 30 min bis 12 h), TLS-Interception im Firmennetz, Sandbox-Lease. Das hat die Bereinigung verlangsamt, nicht verändert.
- **Referenz ohne Menschen.** Alle Precision-Angaben messen die Übereinstimmung mit Claude Haiku 4.5, nicht mit einer menschlichen Wahrheit. Eine ungeprüfte LLM-Fehlerquote geht in alle Zahlen ein.
- **Grobe Recall-Schätzung.** Negative mit Score 0,3–0,5 (18.252): Nach der sehr kleinen, nicht repräsentativen Stichprobe sind es ca. 380 verpasste Handbücher. Das ist **sehr unsicher**; die alte August-Stichprobe, die 22–32 % ergab, stammt vom älteren Modell und gilt für die neuen Scores nicht.

## 6. Empfehlungen für die verbleibende Zeit

1. **Gezielter LLM-Review der 6.464 verdächtigen ungeprüften Dokumente** (Hosts aus `hosts_verdaechtig.csv`, ≈ 15–20 $). Das bringt den größten Precision-Gewinn pro Euro. Der komplette ungeprüfte Rest (13.741) kostet etwa 35 $.
2. **Manuelle Stichprobe** (120 Dokumente, CSV vorbereitet): 20–30 Minuten Arbeit, liefert die einzige echte Genauigkeitsmessung des LLM und stärkt den Bericht erheblich.
3. **Endliste festlegen:** „streng“ (nur LLM-bestätigt) für Qualitätsaussagen, „erweitert“ (inkl. ≥ 0,9) für Mengenaussagen, im Bericht beide nennen.
4. **Optionaler Recall-Schritt** (Negative 0,3–0,5), nur bei Zeitüberschuss: erwarteter Gewinn gering.
5. **Im Bericht als Ausblick:** höhere Schwelle (≥ 0,8) im Live-Crawl, Dateiname als Feature, Nachtraining mit den ≈ 27.000 LLM-Labels (Hard Negatives), Seitenebene statt Dateiebene für JS-Portale.

---

## 7. Abbildungsverzeichnis (Vorschlag für den Bericht)

| Nr. | Datei | Zeigt | Passt zu Kapitel |
|---|---|---|---|
| 01 | `01_trichter.png` | Vom Crawl (164.396 PDFs) über TF-IDF-Positive (44.437) zu LLM-bestätigten (7.367) und geschätzt echten (≈ 18.700) | Ergebnisse / Überblick |
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

Farben: festes Schema über alle Grafiken (blau = LLM-bestätigt, grün = TF-IDF ≥ 0,9 ungeprüft, orange = verworfen, grau = negativ). Die Grafiken sind als PNG mit 200 dpi exportiert.

## 8. Dateien und Reproduzierbarkeit

| Datei | Inhalt |
|---|---|
| `auswertung/build_final.py` | baut `data/final.jsonl` aus allen Läufen, OCR- und LLM-Ergebnissen |
| `auswertung/make_charts.py` | erzeugt alle Grafiken + `data/kennzahlen.json` + Stichprobe |
| `auswertung/data/per_uni_strict.csv`, `per_uni_likely.csv` | Diagnose je Hochschule (Flag, Anzahl, Aktion) |
| `auswertung/data/eval_strict.html`, `eval_likely.html` | vollständiger Evaluationsbericht je Variante |
| `auswertung/hosts_verdaechtig.csv` | Hosts mit ungeprüften Positiven + LLM-Bestätigungsrate |
| `auswertung/stichprobe_manuelle_pruefung.csv` | 120 Dokumente für die manuelle Prüfung (Urteil der Maschine steht in den hinteren Spalten) |

Neu erzeugen (aus dem Repo-Root):

```
python auswertung/build_final.py
.venv\Scripts\python auswertung\make_charts.py
```

Die Evaluationsberichte (`eval_*.html`) entstehen mit `python -m webscraper.evaluation` aus `webscraper/` mit den Manifesten `auswertung/data/eval_strict.jsonl` bzw. `eval_likely.jsonl`.
