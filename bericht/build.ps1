# Baut den Projektbericht komplett neu: Auswertung -> Berichtsgrafiken/Zahlen -> PDF.
# Aufruf aus dem Repo-Root:  pwsh bericht/build.ps1   (Schalter: -SkipAuswertung)
param([switch]$SkipAuswertung)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not $SkipAuswertung) {
    & $py auswertung\build_final.py
    & $py auswertung\make_charts.py
}
& $py bericht\make_report_charts.py
Set-Location (Join-Path $root "bericht")
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
Write-Host "Fertig: bericht\main.pdf"
