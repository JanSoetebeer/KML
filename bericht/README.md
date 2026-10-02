# Projektbericht (LaTeX)

Entwurf des Projektberichts "Webscraper fuer Modulhandbuecher mit AWS".

| Datei | Inhalt |
|---|---|
| `main.tex` | Dokument, Praeambel, Titelseite, Zusammenfassung |
| `kapitel/01..11_*.tex`, `anhang.tex` | Kapitel |
| `bilder/` | Grafiken (PNG, kopiert aus `auswertung/charts/` + eigene `B01..B09`) |
| `bilder/diagramme.tex`, `bilder/architektur.tex` | TikZ: Architektur v1-v3, Datenfluss, Zeitleiste |
| `zahlen.tex` | **generiert**: LaTeX-Makros (`\zDocsTotal`, ...) aus `auswertung/data/kennzahlen.json` |
| `wochen_jan.tex`, `wochen_sascha.tex` | **generiert** aus `daten/stunden.csv` |
| `daten/stunden.csv` | Wochenstunden + Taetigkeiten (von Hand pflegen) |
| `daten/kosten.csv` | Kosten je Posten (von Hand pflegen, Status `schaetzung`/`beleg`) |
| `daten/s3_objekte.csv` | Bucket-Auflistung (git-ignoriert) |
| `make_report_charts.py` | erzeugt Grafiken B01-B09, `zahlen.tex`, Wochentabellen |
| `build.ps1` | komplette Kette bis zum PDF |

## Bauen
```
pwsh bericht/build.ps1            # Auswertung + Berichtsgrafiken + PDF
pwsh bericht/build.ps1 -SkipAuswertung
cd bericht; latexmk -pdf main.tex # nur PDF
```
Voraussetzung: MiKTeX/TeX Live (pdflatex, latexmk, bibtex), `.venv` mit matplotlib.

## Offene Stellen
Im Text sind offene Punkte gelb mit `TODO:` markiert, Platzhalter fuer Sascha Lauk orange `[Sascha Lauk: ...]`.
Suche: `grep -rn "TODO\|saschaPH" bericht/kapitel`.

## Nach Abschluss der LLM-Pruefung
1. `python auswertung/build_final.py` und `make_charts.py` neu laufen lassen (Kennzahlen aktualisieren)
2. `pwsh bericht/build.ps1`
3. Texte, die konkrete Zahlen ausserhalb der Makros nennen, pruefen: Abschnitt "Grenzen" (Kap. 9), Tabelle LLM-Laeufe (Kap. 7), Konfusions-/Precision-Aussagen in Kap. 8 und 11.
