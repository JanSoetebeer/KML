const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require("C:/Users/jan/AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/2498d0e3-0fe1-4cdc-9bc9-7b14e0e9ee78/193b9a0c-c0fd-4c43-a124-9c3dac58b20a/skills/pptx/scripts/apply_theme.js");

const OUT = process.argv[2];
const days = JSON.parse(fs.readFileSync(path.join(__dirname, "days.json"), "utf8"));

const THEME = {
  name: "KML Abschluss",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1F2933", lt1: "FFFFFF", dk2: "1B365D", lt2: "F1F4F8",
    accent1: "2563A8", accent2: "D9731F", accent3: "2E8B57",
    accent4: "5B6573", accent5: "9DBFE3", accent6: "B3261E",
    hlink: "2563A8", folHlink: "5B6573",
  },
};
const H = THEME.colors; // hex values for the few options that cannot take scheme colors

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Abschlusspräsentation – Plattform für Hochschuldokumente";
pres.subject = "Methoden des Machine Learnings, FH Wedel, SS 26";
const C = pres.SchemeColor;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE",
  background: { color: H.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 2.0, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.35, w: 11.7, h: 1.5, fontSize: 20, color: C.background2, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: H.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: 12.13, h: 1.0, fontSize: 28, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.55, h: 0.3, fontSize: 11, color: H.accent4, align: "right" },
});

// ---------------------------------------------------------------- helpers
const X0 = 0.6, CW = 12.13;
function T(slide, text, o) {
  slide.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top", align: "left" }, o));
}
function box(slide, x, y, w, h, fill, name, extra) {
  slide.addShape(pres.shapes.RECTANGLE, Object.assign({ x, y, w, h, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name || "Box" }, extra || {}));
}
function bullets(items, extra) {
  return items.map((t, i) => {
    const isObj = typeof t === "object";
    return { text: isObj ? t.text : t, options: Object.assign({ bullet: true, breakLine: i < items.length - 1 }, isObj ? t.options : {}, extra || {}) };
  });
}
function arrowH(slide, x, y, w, color) {
  slide.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: color || C.accent4, width: 2.5, endArrowType: "triangle" }, objectName: "Pfeil" });
}
function content(title, notes) {
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
}
function chartBase(extra) {
  return Object.assign({
    showLegend: false, showValue: true, showTitle: false,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, dataLabelFontSize: 12,
    catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent4, dataLabelColor: H.dk1,
    valGridLine: { color: "E3E8EE", size: 0.5 }, catGridLine: { style: "none" },
  }, extra);
}
const de = (n) => n.toLocaleString("de-DE");


// ================================================================ neue Backup-Folien
const hc = (t, w) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 14, valign: "middle" } });
const tc = (t, b) => ({ text: t, options: { fontSize: 13, valign: "middle", bold: !!b } });
const TB = { type: "solid", pt: 0.75, color: "D5DBE3" };

function lane(s, x, y, w, h, title, fill) {
  box(s, x, y, w, h, fill, "Lane " + title);
  T(s, title, { x: x + 0.2, y: y + 0.08, w: w - 0.4, h: 0.35, fontSize: 14, bold: true, color: C.text2 });
}
function node(s, x, y, w, h, text, o) {
  o = o || {};
  box(s, x, y, w, h, o.fill || C.background1, "Knoten " + text.split("\n")[0], o.line ? { line: { color: H.accent4, width: 0.75 } } : {});
  T(s, text, { x: x + 0.1, y: y, w: w - 0.2, h, fontSize: 14, bold: !!o.bold, color: o.color || C.text1, align: "center", valign: "middle" });
}
function vArrow(s, x, y1, y2, up) {
  s.addShape(pres.shapes.LINE, { x, y: y1, w: 0, h: y2 - y1, line: { color: C.accent4, width: 2, [up ? "beginArrowType" : "endArrowType"]: "triangle" }, objectName: "Pfeil" });
}
function step(s, x, y, n) {
  s.addShape(pres.shapes.OVAL, { x: x - 0.17, y: y - 0.17, w: 0.34, h: 0.34, fill: { color: C.accent2 }, line: { color: C.accent2, width: 0 }, objectName: "Schritt " + n });
  T(s, String(n), { x: x - 0.17, y: y - 0.17, w: 0.34, h: 0.34, fontSize: 12, bold: true, color: C.background1, align: "center", valign: "middle" });
}


// ======================================================================
// Zusatzfolien (zum Einfügen in die eigene Version)
// ======================================================================
const bd = (t, w) => ({ text: t, options: { bold: true, fontSize: 13, valign: "middle" } });

// ---------------------------------------------------------------- A1 Warum eine eigene Plattform
{
  const s = content("Warum eine eigene Plattform – und nicht einfach ChatGPT?",
    "[0:45] Nur kurz, aber selbstbewusst. Die Frage kommt garantiert: 'Warum bauen Sie das, wenn ich ChatGPT fragen kann?'\n" +
    "Antwort in einem Satz: Ein Chat-Assistent liefert Antworten – unsere Plattform liefert einen belegbaren, wiederholbaren Datenbestand.\n" +
    "1. Überwachbar: Jeder Schritt ist protokolliert, jede Entscheidung ist sichtbar und korrigierbar (Review-Oberfläche). Ein Chat ist eine Blackbox.\n" +
    "2. Deterministisch: Gleiche Eingabe, gleicher Ablauf: regelbasierter Crawler, festes Modell, feste Schwellen. Ein Chat gibt bei jeder Frage eine andere Antwort und kann nicht zuverlässig hunderte Webseiten durchlaufen und PDFs speichern.\n" +
    "3. Dokumentierbar: Pro Dokument gibt es Quelle, Zeitpunkt, Score und Begründung – das ist zitierbar und damit wissenschaftlich nutzbar.\n" +
    "4. Skalierbar und kontrollierbar: 164.396 PDFs von 404 Hochschulen für 155 $, Qualität messbar (Precision, Recall), beliebig wiederholbar.\n" +
    "Wichtig: Wir verzichten nicht auf Sprachmodelle – wir setzen sie gezielt als zweite Stufe ein, kontrolliert und protokolliert.");
  const items = [
    ["Überwachbar", "Jeder Schritt ist protokolliert, jede Entscheidung sichtbar und korrigierbar. Ein Chat-Assistent bleibt eine Blackbox."],
    ["Deterministisch", "Gleiche Eingabe, gleicher Ablauf: regelbasierter Crawler, festes Modell, feste Schwellen. Ein Chat antwortet jedes Mal anders."],
    ["Dokumentierbar", "Pro Dokument: Quelle, Zeitpunkt, Score und Begründung. Zitierbar und damit für Forschung belegbar."],
    ["Skalierbar", "164.396 PDFs von 404 Hochschulen für 155 $. Qualität messbar, beliebig wiederholbar, Dokumente in eigener Hand."],
  ];
  items.forEach((it, i) => {
    const x = X0 + i * 3.08;
    box(s, x, 1.55, 2.9, 3.7, C.background2, "Vorteil " + (i + 1));
    T(s, it[0], { x: x + 0.2, y: 1.75, w: 2.5, h: 0.5, fontSize: 21, bold: true, color: C.accent1 });
    T(s, it[1], { x: x + 0.2, y: 2.4, w: 2.5, h: 2.7, fontSize: 15 });
  });
  T(s, "Ein Chat-Assistent liefert Antworten – die Plattform liefert einen belegbaren, wiederholbaren Datenbestand.", { x: X0, y: 5.45, w: CW, h: 0.8, fontSize: 20, bold: true, color: C.text2 });
  T(s, "Sprachmodelle nutzen wir trotzdem: gezielt als zweite Stufe, kontrolliert und protokolliert.", { x: X0, y: 6.35, w: CW, h: 0.4, fontSize: 15, color: C.accent4 });
}

// ---------------------------------------------------------------- A2 Projektverlauf & Vorgehen
{
  const s = content("Projektverlauf und Vorgehen: wochenweise Sprints, testen und verbessern",
    "[1:30] Hier zeigst du den Arbeitsumfang UND die Arbeitsweise.\n" +
    "Vorgehen: 17 Wochen (KW 24 bis KW 40), jede Woche ein Sprint mit einem klaren Ziel. Agil heißt bei uns: Wir haben nicht alles vorab geplant, sondern jede Woche am echten Setup getestet, ausgewertet und verbessert.\n" +
    "Beispiel für die Schleife: Der erste Großlauf lieferte nur etwa 12.000 Treffer statt der erwarteten ca. 40.000. Die Recall-Analyse zeigte 145 Hochschulen ohne Treffer. Daraus entstanden Discovery (Common Crawl, Serper), OCR und die Sprachmodell-Stufe. Der Deep Run holte danach 132.187 PDFs. Bei der Auswertung fanden wir sogar einen Fehler in unserer eigenen Auswertung und korrigierten ihn.\n" +
    "Phasen: 1 Prototyp und Cloud (Juni–Juli), 2 MVP (Juli), 3 Großlauf und Qualität (August–September), 4 Deep Run und Auswertung (September–Oktober).\n" +
    "Details zum Funktionsumfang: Backup-Folie 'Funktionsumfang'.");
  // Zyklus
  const cyc = ["Wochenziel planen", "Bauen", "Am echten Setup testen", "Auswerten und verbessern"];
  cyc.forEach((c, i) => {
    const x = X0 + i * 3.08;
    box(s, x, 1.5, 2.85, 0.8, i === 2 ? C.accent1 : C.background2, "Zyklus " + (i + 1));
    T(s, c, { x: x + 0.1, y: 1.5, w: 2.65, h: 0.8, fontSize: 16, bold: true, color: i === 2 ? C.background1 : C.text2, align: "center", valign: "middle" });
    if (i < 3) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.87, y: 1.78, w: 0.2, h: 0.25, fill: { color: C.accent4 }, line: { color: C.accent4, width: 0 }, objectName: "Pfeil" });
  });
  T(s, "17 Wochen Sprints (KW 24–40): agil, jede Woche testen und verbessern", { x: X0, y: 2.4, w: CW, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  const ph = [
    ["Phase 1 · Juni–Juli", "Prototyp & Cloud", ["Scrapy-Prototyp", "AWS: Lambda, S3, DynamoDB", "Login, Rollen, Webapp"]],
    ["Phase 2 · Juli", "MVP", ["Erster Klassifikator", "Review-Oberfläche, Nachtraining", "CI/CD, fokussierter Crawl"]],
    ["Phase 3 · August–September", "Großlauf & Qualität", ["Erster Großlauf: ≈ 12 Tsd. statt 40 Tsd.", "Recall-Analyse: 145 Hochschulen ohne Treffer", "→ Discovery, OCR, Sprachmodell-Stufe"]],
    ["Phase 4 · September–Oktober", "Deep Run & Auswertung", ["Deep Run: 132.187 PDFs in 13 h", "Prüfung von ≈ 34.000 Dokumenten", "Fehler in eigener Auswertung korrigiert"]],
  ];
  ph.forEach((p, i) => {
    const x = X0 + i * 3.08;
    box(s, x, 2.9, 2.9, 3.5, C.background2, "Phase " + (i + 1));
    T(s, p[0], { x: x + 0.2, y: 3.0, w: 2.5, h: 0.35, fontSize: 13, bold: true, color: C.accent1 });
    T(s, p[1], { x: x + 0.2, y: 3.4, w: 2.5, h: 0.7, fontSize: 19, bold: true, color: C.text2 });
    T(s, bullets(p[2]), { x: x + 0.2, y: 4.2, w: 2.5, h: 2.1, fontSize: 14, paraSpaceAfter: 6 });
  });
}

// ---------------------------------------------------------------- A3 Live-Demo
{
  const s = content("Live-Demo: so läuft sie ab",
    "[ca. 2:00] Selbstbewusst ankündigen: 'Im nächsten Schritt zeigen wir die Anwendung in einer Live-Demo. Das Setup wurde vorab getestet.'\n" +
    "VOR DEM VORTRAG: 1. Webapp-Login testen (https://52.57.68.217, Zertifikatswarnung bestätigen). 2. Lambda warmlaufen lassen (einen kurzen Test-Lauf starten) – kalte Starts dauern deutlich länger. 3. Demo-URL(s) bereithalten, die noch nicht besucht wurden (sonst: 'already in visited store'). 4. Screenshots als Fallback griffbereit.\n" +
    "Ablauf: 1 anmelden, 2 Einstiegs-URL eintragen und Dateiformat pdf wählen, 3 Lauf starten, 4 Ergebnisse mit Score und Entscheidung zeigen, 5 im Prüfband ein Urteil per Klick abgeben (fließt ins Nachtraining).\n" +
    "Falls etwas klemmt: souverän weiter mit den Screenshots der nächsten Folie: 'So sieht das normalerweise aus.'");
  const st = [["1", "Anmelden", "Webapp im Browser, Login mit Rolle"], ["2", "URL eintragen", "Einstiegsseite einer Hochschule, Dateiformat pdf"], ["3", "Lauf starten", "Crawler läuft in der Cloud, ca. 30 Sekunden"], ["4", "Ergebnisse", "Dokumente mit Score und Entscheidung"], ["5", "Prüfband", "Mensch entscheidet per Klick, Urteil fließt ins Nachtraining"]];
  st.forEach((x, i) => {
    const px = X0 + i * 2.48;
    box(s, px, 1.7, 2.2, 3.2, i === 2 ? C.accent5 : C.background2, "Demo " + x[0]);
    T(s, x[0], { x: px + 0.2, y: 1.85, w: 1, h: 0.7, fontSize: 36, bold: true, color: C.accent1 });
    T(s, x[1], { x: px + 0.2, y: 2.65, w: 1.8, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    T(s, x[2], { x: px + 0.2, y: 3.2, w: 1.8, h: 1.6, fontSize: 14 });
    if (i < 4) s.addShape(pres.shapes.RIGHT_ARROW, { x: px + 2.22, y: 3.1, w: 0.24, h: 0.4, fill: { color: C.accent4 }, line: { color: C.accent4, width: 0 }, objectName: "Pfeil" });
  });
  T(s, "Fallback: Screenshots auf der nächsten Folie.", { x: X0, y: 5.3, w: CW, h: 0.5, fontSize: 20, bold: true, color: C.text2 });
}

// ---------------------------------------------------------------- A4 Warum 63 %
{
  const s = content("Warum „nur“ 63 %? Die Abdeckung richtig einordnen",
    "[1:30] Das ist die Folie, die das 'eher schlechte' Ergebnis souverän einordnet. Nicht entschuldigen – erklären.\n" +
    "Kernaussage: 63 % der Hochschulen haben mindestens ein bestätigtes Modulhandbuch – bei einer ersten automatisierten Vollerhebung ohne vergleichbare zentrale Sammlung. Wo die Daten öffentlich und gut verlinkt sind, funktioniert es sehr gut: öffentlich-rechtliche Hochschulen 78 %, Universitäten 76 %, Hochschulen mit 15.000–30.000 Studierenden 97 %.\n" +
    "Gründe für die Lücken: (1) Kleine und private Hochschulen veröffentlichen kaum PDFs: Handbücher liegen hinter Login, in JavaScript-Portalen oder Suchmasken. (2) 39 Hochschulen blieben ganz ohne Fund. (3) Wir zählen streng: Prüfungsordnungen, Einzelmodulblätter und Studienverlaufspläne sind keine Modulhandbücher – bewusst auf Precision optimiert (≈ 98 %). (4) Der Crawler ist höflich: robots.txt, Drosselung, Seitenbudget.\n" +
    "Recall ehrlich: ≈ 16.300 eindeutige Dokumente von ≈ 40.000 laut Fachschätzung (Größenordnung, keine Messung), also etwa 40 %.\n" +
    "Überleitung: 'Wir haben dafür sehr viele Techniken ausprobiert – die nächste Folie zeigt, was gewirkt hat.'");
  box(s, X0, 1.5, 6.4, 4.9, C.background2, "Gründe");
  T(s, "Warum es Lücken gibt", { x: X0 + 0.25, y: 1.65, w: 5.9, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  T(s, bullets([
    { text: "Kleine und private Hochschulen: kaum PDFs, Handbücher hinter Login, in JavaScript-Portalen oder Suchmasken (Abdeckung 44 % bzw. 39 %)", options: {} },
    "39 Hochschulen ohne jeden Fund",
    "Strenge Definition: Prüfungsordnungen, Einzelblätter und Verlaufspläne zählen nicht – bewusst auf Precision (≈ 98 %) optimiert",
    "Höflicher Crawler: robots.txt, Drosselung, Seitenbudget",
    "Recall ≈ 40 % der Fachschätzung (≈ 16.300 von ≈ 40.000, keine Messung)",
  ]), { x: X0 + 0.25, y: 2.15, w: 5.9, h: 4.2, fontSize: 15, paraSpaceAfter: 9 });
  T(s, "Wo es gut funktioniert", { x: 7.3, y: 1.5, w: 5.4, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  const f = [["78 %", "öffentlich-rechtliche Hochschulen"], ["76 %", "Universitäten"], ["97 %", "Hochschulen mit 15–30 Tsd. Studierenden"], ["63 %", "alle 404 Hochschulen (255 mit ≥ 1 Handbuch)"]];
  f.forEach((t, i) => {
    const x = 7.3 + (i % 2) * 2.75, y = 2.0 + Math.floor(i / 2) * 2.15;
    box(s, x, y, 2.6, 2.0, C.background2, "Wert " + (i + 1));
    T(s, t[0], { x: x + 0.15, y: y + 0.15, w: 2.3, h: 0.8, fontSize: 36, bold: true, color: C.accent1, valign: "middle" });
    T(s, t[1], { x: x + 0.15, y: y + 1.0, w: 2.3, h: 0.95, fontSize: 14 });
  });
  T(s, "Nach unserer Recherche gibt es keine vergleichbare zentrale Sammlung – jede gefundene Datei ist ein Gewinn gegenüber Null.", { x: 7.3, y: 6.3, w: 5.4, h: 0.6, fontSize: 13, color: C.accent4 });
}

// ---------------------------------------------------------------- A5 Techniken
{
  const s = content("Was wir probiert haben: Techniken und ihre Wirkung",
    "[1:30] Zeigt die Breite der Arbeit: viele neue Techniken, ehrlich bewertet – auch das, was wenig gebracht hat.\n" +
    "Wirksam: Zweistufige Klassifikation (Precision von 25 % auf ≈ 98 %), Best-First-Crawl mit Sitemaps und Fakultäts-Subdomains, Host-Analyse (verdächtige Hosts, Precision 89 % → 98 %), Common Crawl (ca. 60 % der gescheiterten Domains in Tests geborgen), Serper (13 Handbücher bei drei Hochschulen mit null Treffern), Fargate-Bulk mit Watchdog und Breadth-Fairness (FernUni Hagen: 70 → 870 Dokumente), Human-in-the-Loop mit Nachtraining.\n" +
    "Begrenzt: Seeds-only-Modus (nur 345 neue Dokumente), OCR (3.553 Scans, nur 42 zusätzliche Treffer – hoher Aufwand, kleiner Ertrag).\n" +
    "Offen: Firecrawl für JavaScript-Portale (gebaut, noch kein Großeinsatz).\n" +
    "Kurz erklärt: Watchdog = Kostenschutz, der einen hängenden Großlauf nach spätestens 6 Stunden hart beendet. Breadth-Fairness = das Seitenbudget wird auf alle Fakultäten verteilt, statt dass der Crawler in der ersten ergiebigen Ecke steckenbleibt. Discovery = Suche außerhalb des Crawls (Common Crawl, Serper), deren URLs als Seeds in den Crawler gehen. Common Crawl = kostenloser öffentlicher Webindex. Serper = Google-Suche per Schnittstelle. Firecrawl = rendert JavaScript-Seiten.\n" +
    "Botschaft: Wir haben systematisch getestet, gemessen und das Unwirksame benannt – das ist Teil des Ergebnisses.");
  const hh = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 13, valign: "middle" } });
  const nm = (t) => ({ text: t, options: { fontSize: 12, bold: true, valign: "middle" } });
  const tx = (t) => ({ text: t, options: { fontSize: 12, valign: "middle" } });
  const ok = (t) => ({ text: t, options: { fontSize: 12, bold: true, color: C.accent3, valign: "middle" } });
  const mid = (t) => ({ text: t, options: { fontSize: 12, bold: true, color: C.accent2, valign: "middle" } });
  const op = (t) => ({ text: t, options: { fontSize: 12, bold: true, color: C.accent4, valign: "middle" } });
  const rows = [
    [hh("Technik"), hh("Was es ist (kurz)"), hh("Wirkung"), hh("Bewertung")],
    [nm("Zwei Stufen"), tx("Schnelles ML-Modell sortiert vor, Sprachmodell prüft nur die Grauzone"), tx("Precision 25 % → ≈ 98 %"), ok("wirksam")],
    [nm("Host-Analyse"), tx("Server mit < 30 % Bestätigung werden komplett nachgeprüft"), tx("Endliste ≈ 89 % → ≈ 98 %"), ok("wirksam")],
    [nm("Best-First, Sitemaps, Subdomains"), tx("Wichtige Links zuerst; Sitemaps als Einstieg; Fakultätsserver extra"), tx("Handbuch-Seiten früher gefunden"), ok("wirksam")],
    [nm("Fargate-Bulk"), tx("Container-Dienst: viele Hochschulen parallel in Großläufen"), tx("10–14 Tsd. PDFs/h"), ok("wirksam")],
    [nm("Watchdog"), tx("Kostenschutz: beendet hängende Großläufe nach spätestens 6 h"), tx("keine endlos laufenden Kosten"), ok("wirksam")],
    [nm("Breadth-Fairness"), tx("Budget auf alle Fakultäten verteilt statt in einer festzuhängen"), tx("FernUni Hagen 70 → 870"), ok("wirksam")],
    [nm("Discovery"), tx("Suche außerhalb des Crawls: liefert Dokument-URLs als Seeds"), tx("füllt Lücken des Crawls"), ok("wirksam")],
    [nm("Common Crawl"), tx("Kostenloser öffentlicher Webindex mit bekannten Dokument-URLs"), tx("≈ 60 % der gescheiterten Domains"), ok("wirksam")],
    [nm("Serper"), tx("Google-Suche per Schnittstelle (Begriff + Domain + PDF)"), tx("13 Funde bei 3 Test-Hochschulen"), ok("wirksam")],
    [nm("Firecrawl"), tx("Rendert JavaScript-Seiten wie ein Browser, um Links zu finden"), tx("gebaut, kein Großeinsatz"), op("offen")],
    [nm("OCR"), tx("Texterkennung für gescannte PDFs ohne Textebene"), tx("3.553 Scans → 42 Treffer"), mid("begrenzt")],
    [nm("Seeds-only-Modus"), tx("Holt nur per Discovery gefundene URLs, ohne Link-Crawl"), tx("nur 345 neue Dokumente"), mid("begrenzt")],
    [nm("Human-in-the-Loop"), tx("Mensch entscheidet per Klick; Urteil fließt ins Nachtraining"), tx("Review-UI und Retrain gebaut"), ok("wirksam")],
  ];
  s.addTable(rows, { x: X0, y: 1.3, w: CW, colW: [2.4, 5.7, 2.8, 1.23], rowH: [0.4].concat(Array(13).fill(0.4)), border: TB, margin: [0.02, 0.1, 0.02, 0.1], objectName: "Tabelle Techniken" });
}

// ---------------------------------------------------------------- B1 Verdächtige Hosts
{
  const s = content("Backup: Was sind „verdächtige Hosts“?",
    "Ein Host ist der Server bzw. die Teilseite einer Hochschule, zum Beispiel www.uni-hamburg.de oder cs.tu-dortmund.de. Verdächtig nennen wir einen Host, auf dem das Sprachmodell bei mindestens 10 geprüften Dokumenten weniger als 30 % als Modulhandbuch bestätigt hat (Definition in auswertung/prep_suspect.py). Warum das wichtig ist: Auf solchen Hosts liegen viele Prüfungsordnungen, Vorlesungsverzeichnisse oder Einzelblätter, die dem ML-Modell sehr ähnlich erscheinen. Deshalb sind selbst Dokumente mit hohem Score (ab 0,9) dort unzuverlässig. Wir haben alle 6.463 ungeprüften Dokumente mit Score ab 0,9 auf 197 solchen Hosts vollständig vom Sprachmodell prüfen lassen: Nur 68 % wurden bestätigt, auf den übrigen Hosts waren es 94,2 %. Dieses gezielte Nachprüfen hob die geschätzte Precision der Endliste von ca. 89 % auf ca. 98 %, ohne alle 13.700 ungeprüften Dokumente zu prüfen – ein günstiger, gezielter Qualitätshebel.");
  box(s, X0, 1.5, 6.3, 2.6, C.background2, "Definition");
  T(s, [
    { text: "Host ", options: { bold: true } }, { text: "= Server bzw. Teilseite einer Hochschule, z. B. www.uni-hamburg.de oder cs.tu-dortmund.de.", options: { breakLine: true } },
    { text: "Verdächtig ", options: { bold: true } }, { text: "= Host, auf dem das Sprachmodell bei mindestens 10 geprüften Dokumenten weniger als 30 % bestätigt hat.", options: { breakLine: true } },
    { text: "Warum: ", options: { bold: true } }, { text: "dort sind auch Dokumente mit hohem Score unzuverlässig (Prüfungsordnungen, Verzeichnisse, Einzelblätter).", options: {} },
  ], { x: X0 + 0.25, y: 1.6, w: 5.8, h: 2.4, fontSize: 15, paraSpaceAfter: 8 });
  const rows = [
    [hc("Beispiel-Host"), hc("geprüft"), hc("bestätigt")],
    [tc("www.uni-hamburg.de"), tc("513"), tc("7 %")],
    [tc("www.uni-flensburg.de"), tc("284"), tc("11 %")],
    [tc("www.tu-braunschweig.de"), tc("195"), tc("11 %")],
    [tc("www.hcu-hamburg.de"), tc("94"), tc("12 %")],
  ];
  s.addTable(rows, { x: X0, y: 4.3, w: 6.3, colW: [3.5, 1.4, 1.4], rowH: 0.42, border: TB, margin: [0.03, 0.12, 0.03, 0.12], objectName: "Tabelle Hosts" });
  T(s, "Beispiele: Hosts mit ≥ 10 geprüften Dokumenten und < 30 % Bestätigung.", { x: X0, y: 6.5, w: 6.3, h: 0.3, fontSize: 11, color: C.accent4 });
  T(s, "Bestätigungsrate bei Score ≥ 0,9", { x: 7.2, y: 1.5, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: "Bestätigt", labels: ["Verdächtige Hosts (197)", "Übrige Hosts"], values: [68, 94.2] }],
    chartBase({ x: 7.2, y: 1.95, w: 5.5, h: 3.4, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 110, chartColors: [H.accent2, H.accent3], dataLabelFormatCode: '0.0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 60, dataLabelFontSize: 15, catAxisLabelFontSize: 13 }));
  box(s, 7.2, 5.5, 5.5, 1.3, C.background2, "Wirkung");
  T(s, "6.463 Dokumente gezielt nachgeprüft: Precision der Endliste ≈ 89 % → ≈ 98 %, ohne alle 13.700 ungeprüften Dokumente zu prüfen.", { x: 7.4, y: 5.55, w: 5.1, h: 1.2, fontSize: 14, bold: true, color: C.text2, valign: "middle" });
}

// ---------------------------------------------------------------- B2 Ethical Crawling & Seeds-only
{
  const s = content("Backup: Ethical Crawling – wo im Projekt, und was Seeds-only bedeutet",
    "Wo findet man das im Projekt? Kurzfassung: webscraper/webscraper/settings.py, Abschnitt 'Ethical scraping' (ROBOTSTXT_OBEY = True), dazu Drosselung (1 s Verzögerung, AutoThrottle bis 10 s, 2 Anfragen je Domain), die Middleware polite_middleware.py (identifizierender User-Agent), die Domain-Grenze im Spider (_same_site), Seitenbudget (Tiefe 2, 60 Seiten), der DynamoDB-Visited-Store gegen Mehrfachabrufe sowie Dateigröße 50 MB und Timeout 60 s. Im Projektbericht: Kapitel 6, Abschnitte 'robots.txt und Seeds' und 'Höflichkeit und Grenzen'.\n" +
    "Seeds-only-Modus: Zuerst findet die Discovery per Common Crawl und Serper öffentlich indexierte Dokument-URLs je Hochschul-Domain. Der Seeds-only-Lauf holt nur diese URLs direkt – ohne Link-Crawl und ohne Sitemaps der Seite. Es gab drei Seeds-Läufe (03.–16.09.) mit 431, 135 und 215 URLs; nur 345 Dokumente waren in keinem anderen Lauf enthalten.\n" +
    "Robots-Ausnahme: Der Schalter SEEDS_BYPASS_ROBOTS (seit 16.09., Commit a633085; GitHub-Workflow-Eingabe seeds_bypass_robots) ist standardmäßig AUS. Eingeschaltet übergeht er robots.txt NUR für die einzelnen Seed-URLs, die ein Suchindex bereits als öffentlich ausweist; der Link-Crawl der Seite respektiert robots.txt weiterhin. Anlass: Uni Konstanz mit 'Disallow: /' – im Test 13 von 18 Dateien. Das ist eine bewusste Abwägung, die im Bericht (Kapitel 6 und Diskussion) offen benannt wird; vor einer Veröffentlichung des Datensatzes rechtlich bewerten. Welche Läufe den Schalter tatsächlich nutzten, steht in den Workflow-Eingaben der jeweiligen GitHub-Actions-Läufe.");
  const hh = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 14, valign: "middle" } });
  const rows = [
    [hh("Regel"), hh("Wo im Projekt")],
    [tc("robots.txt befolgen", true), tc("settings.py, Abschnitt „Ethical scraping“: ROBOTSTXT_OBEY = True")],
    [tc("Drosselung", true), tc("settings.py: 1 s Verzögerung, AutoThrottle bis 10 s, 2 Anfragen je Domain")],
    [tc("User-Agent", true), tc("middlewares/polite_middleware.py")],
    [tc("Domain-Grenze, Budget", true), tc("spiders/document_spider.py: _same_site, Tiefe 2, 60 Seiten")],
    [tc("Keine Mehrfachabrufe", true), tc("state/visited_store.py (DynamoDB)")],
    [tc("Beschreibung", true), tc("Projektbericht Kap. 6: „robots.txt und Seeds“, „Höflichkeit und Grenzen“")],
  ];
  s.addTable(rows, { x: X0, y: 1.5, w: 6.5, colW: [2.1, 4.4], rowH: [0.45, 0.8, 0.8, 0.55, 0.8, 0.55, 0.8], border: TB, margin: [0.03, 0.1, 0.03, 0.1], objectName: "Tabelle Ethik" });
  box(s, 7.3, 1.5, 5.43, 5.3, C.background2, "Seeds-only");
  T(s, "Was ist der Seeds-only-Modus?", { x: 7.5, y: 1.62, w: 5.0, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  T(s, bullets([
    "Discovery findet über Common Crawl und Serper öffentlich indexierte Dokument-URLs je Hochschule",
    "Der Lauf holt nur diese URLs direkt – kein Link-Crawl, keine Sitemaps",
    "3 Läufe (03.–16.09.): 431 / 135 / 215 URLs, nur 345 Dokumente neu",
    "Schalter SEEDS_BYPASS_ROBOTS (seit 16.09.): standardmäßig aus; übergeht robots.txt nur für diese Seed-URLs (Anlass: Uni Konstanz, Disallow: /)",
    "Bewusste Abwägung; vor Veröffentlichung des Datensatzes rechtlich bewerten",
  ]), { x: 7.5, y: 2.1, w: 5.0, h: 4.6, fontSize: 14, paraSpaceAfter: 8 });
}

// ---------------------------------------------------------------- B3 Modularität Überblick
{
  const s = content("Backup: Modularität – austauschbar und Aufwand je Use Case",
    "Kernbotschaft: Die Plattform besteht aus einem festen Teil und vier austauschbaren Teilen.\n" +
    "FEST (bleibt für jeden Use Case gleich): Crawl-Engine (Scrapy: Tiefe, Budget, robots.txt, Deduplizierung), Cloud-Betrieb (Lambda/Fargate, S3, DynamoDB), Hochschulliste, Webapp mit Review-Oberfläche, Evaluationsmodul.\n" +
    "AUSTAUSCHBAR (je Use Case): 1. Das Extraction Profile (profiles/*.py, Registry in profiles/registry.py): Was folgen, was herunterladen, was extrahieren? Beim Modulhandbuch-Profil sind das ca. 70 Zeilen: Schlüsselwörter mit Gewichten, Zieldateien, Suchbegriffe für die Discovery. 2. Die Discovery-Begriffe (im Profil). 3. Die Spec für das Sprachmodell (mlclassifier/specs.py): Definition und Gegenbeispiele als Text, wenige Zeilen. 4. Optional das ML-Modell: Für den Start reichen die Sprachmodell-Urteile als Labels; danach lässt sich ein schnelles ML-Modell trainieren.\n" +
    "Konkret für KI-Richtlinien (Bachelorarbeit): neues Profil mit Schlüsselwörtern wie 'KI', 'Richtlinie', 'generative'; neue Spec 'ki_richtlinie'; Lauf über dieselbe Hochschulliste starten; Ergebnisse im Review prüfen. Es muss kein Crawler neu gebaut werden.\n" +
    "Aufwandsangaben sind Schätzungen. Auswahl des Profils: Parameter --profile / CRAWL_PROFILE / Lambda-Event 'profile' / Fargate-Umgebungsvariable.");
  box(s, X0, 1.5, 5.6, 1.9, C.background2, "Fest");
  T(s, [
    { text: "Bleibt gleich", options: { bold: true, color: C.text2, breakLine: true, fontSize: 16 } },
    { text: "Crawl-Engine · Cloud-Betrieb · Hochschulliste · Webapp mit Review · Evaluation", options: {} },
  ], { x: X0 + 0.25, y: 1.6, w: 5.1, h: 1.7, fontSize: 15, paraSpaceAfter: 6 });
  T(s, "Austauschbar – je Use Case", { x: X0, y: 3.55, w: 5.6, h: 0.35, fontSize: 16, bold: true, color: C.accent1 });
  const plug = [["① Profil", "Was folgen, laden, extrahieren"], ["② Discovery", "Suchbegriffe im Profil"], ["③ Spec", "Prompt für das Sprachmodell"], ["④ ML-Modell", "optional, später trainiert"]];
  plug.forEach((p, i) => {
    const x = X0 + (i % 2) * 2.8, y = 4.0 + Math.floor(i / 2) * 1.4;
    box(s, x, y, 2.65, 1.25, C.accent1, "Plug " + (i + 1));
    T(s, [{ text: p[0], options: { bold: true, breakLine: true, fontSize: 16 } }, { text: p[1], options: {} }], { x: x + 0.15, y: y, w: 2.35, h: 1.25, fontSize: 14, color: C.background1, valign: "middle" });
  });
  const rows = [
    [hc("Schritt"), hc("Was zu tun ist"), hc("Aufwand*")],
    [tc("① Profil", true), tc("Python-Klasse (Modulhandbuch: ca. 70 Zeilen): Schlüsselwörter mit Gewichten, Zieldateien, Suchbegriffe; in registry.py eintragen"), tc("Stunden")],
    [tc("③ Spec", true), tc("Definition und Gegenbeispiele als Text (wenige Zeilen), in specs.py eintragen; an Beispielen verfeinern"), tc("Stunden")],
    [tc("④ Modell", true), tc("optional: Start mit Sprachmodell-Urteilen (≈ 3 $ je 1.000 Dokumente) und Review, später ML-Modell trainieren"), tc("Tage")],
    [tc("Betrieb", true), tc("Hochschulliste hochladen, Lauf mit Profil starten, Ergebnisse im Review prüfen – unverändert"), tc("Minuten")],
  ];
  s.addTable(rows, { x: 6.5, y: 1.5, w: 6.23, colW: [1.1, 4.0, 1.13], rowH: [0.45, 1.15, 1.0, 1.15, 1.0], border: TB, margin: [0.03, 0.1, 0.03, 0.1], objectName: "Tabelle Use Case" });
  T(s, "* Schätzungen. Beispiel KI-Richtlinien (Bachelorarbeit): neues Profil + neue Spec, derselbe Crawler.", { x: 6.5, y: 6.35, w: 6.23, h: 0.5, fontSize: 12, color: C.accent4 });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})();
