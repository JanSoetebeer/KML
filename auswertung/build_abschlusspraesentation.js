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

// ================================================================ 1 Titel
{
  const s = pres.addSlide({ masterName: "TITLE" });
  s.addText("Eine Plattform, die Hochschuldokumente sammelt, prüft und nutzbar macht", { placeholder: "title" });
  s.addText([
    { text: "Erster Anwendungsfall: Modulhandbücher deutscher Hochschulen", options: { breakLine: true } },
    { text: "Abschlusspräsentation · Methoden des Machine Learnings · FH Wedel · SS 26", options: {} },
  ], { placeholder: "body", paraSpaceAfter: 8 });
  s.addNotes(
    "[0:20] Souverän starten, keine Entschuldigung, keine Scherze über die Zeit der Zuhörenden.\n" +
    "Einstieg: 'Wir stellen Ihnen heute eine Plattform vor, die einen Datenschatz erschließt, den es in Deutschland so bisher nicht gibt – und zeigen, was damit schon erreicht ist.'\n" +
    "Wichtig: Es geht nicht um Scraping als Selbstzweck, sondern um die Infrastruktur dahinter. Modulhandbücher sind der erste Anwendungsfall, nicht der einzige.\n" +
    "Gesamtdauer: ca. 20 Minuten, danach Fragen."
  );
}

// ================================================================ 2 Warum
{
  const s = content("Warum? Ein Datenschatz, den es bisher nicht gibt",
    "[1:30] Das 'Warum' ist die wichtigste Folie – nimm dir die Zeit.\n" +
    "Kernaussage: Nicht das Sammeln ist der Wert, sondern das, was danach möglich wird. Heute liegen die Modulhandbücher von über 400 Hochschulen verstreut auf tausenden Webseiten. Es gibt kein Verzeichnis, keine Schnittstelle, keine zentrale Sammlung – nach unserer Recherche auch nirgends in vergleichbarer Form.\n" +
    "Unsere Plattform macht daraus eine geprüfte, wiederholbare Datengrundlage. Darauf können Forschung, Lehre und Folgeprojekte direkt aufbauen, statt jedes Mal bei null zu starten.\n" +
    "Kurz erklären: Ein Modulhandbuch beschreibt alle Module eines Studiengangs – Inhalte, Umfang in ECTS, Prüfungsformen. Es ist die Quelle, um Lehre zwischen Hochschulen zu vergleichen.");
  const bw = 3.5, by = 1.65, bh = 2.75, xs = [0.6, 4.92, 9.23];
  const heads = ["Heute: verstreut", "Unsere Plattform", "Morgen: Datenschatz"];
  const texts = [
    "Modulhandbücher von 404 Hochschulen liegen auf tausenden Webseiten – jede anders aufgebaut, ohne zentrales Verzeichnis und ohne Schnittstelle.",
    "Findet, lädt, prüft und speichert die Dokumente automatisch – wiederholbar, nachvollziehbar und für neue Dokumenttypen erweiterbar.",
    "Eine geprüfte Datengrundlage, auf der Forschung, Lehre und Folgeprojekte direkt aufbauen können – statt jedes Mal bei null zu starten.",
  ];
  heads.forEach((h, i) => {
    const mid = i === 1;
    box(s, xs[i], by, bw, bh, mid ? C.accent1 : C.background2, "Karte " + (i + 1));
    T(s, h, { x: xs[i] + 0.3, y: by + 0.25, w: bw - 0.6, h: 0.5, fontSize: 22, bold: true, color: mid ? C.background1 : C.text2 });
    T(s, texts[i], { x: xs[i] + 0.3, y: by + 0.95, w: bw - 0.6, h: 1.65, fontSize: 16, color: mid ? C.background1 : C.text1 });
  });
  [4.12, 8.43].forEach((x) => s.addShape(pres.shapes.RIGHT_ARROW, { x, y: by + 1.1, w: 0.6, h: 0.55, fill: { color: C.accent4 }, line: { color: C.accent4, width: 0 }, objectName: "Pfeil" }));
  T(s, "Der Wert liegt nicht im Sammeln, sondern in dem, was danach möglich wird.", { x: X0, y: 4.85, w: CW, h: 0.6, fontSize: 26, bold: true, color: C.text2 });
  T(s, "Modulhandbuch = Beschreibung aller Module eines Studiengangs: Inhalte, Umfang (ECTS) und Prüfungsformen.", { x: X0, y: 5.75, w: CW, h: 0.4, fontSize: 15, color: C.accent4 });
}

// ================================================================ 3 User Stories
{
  const s = content("Wer profitiert? Vier Nutzergruppen, ein gemeinsamer Datenbestand",
    "[2:00] Hier rechtfertigst du das Projekt über konkrete Nutzer.\n" +
    "1. Doktorprojekt: Der Datenbestand ist Grundlage für empirische Vergleiche zwischen Hochschulen – ohne dass jemand selbst crawlen muss.\n" +
    "2. Professor:innen mit Lehrmaterialien und Projekten: Sie können ihre Lehre an realen Curricula anderer Hochschulen ausrichten und vergleichen.\n" +
    "3. Studiengangsentwicklung an der FH Wedel: Das war die ursprüngliche User Story des Projekts.\n" +
    "4. Neu: Heute wurde ein Bachelorarbeits-Vorschlag eingereicht. Ein Student soll die Plattform erweitern und statt Modulhandbüchern die KI-Richtlinien der Hochschulen erheben. Das ist der Beweis, dass die Plattform wiederverwendbar ist: neues Extraktionsprofil, kein neuer Crawler.\n" +
    "Überleitung: 'Vier unterschiedliche Nutzer, aber ein gemeinsamer Bedarf: eine zentrale, geprüfte Datenbasis.'");
  const cw = 5.95, ch = 2.2, xs = [0.6, 6.78], ys = [1.55, 3.95];
  const cards = [
    ["DOKTORPROJEKT", "Als Doktorand möchte ich Hochschuldokumente flächendeckend und strukturiert vorliegen haben, um Hochschulen empirisch zu vergleichen – ohne selbst zu crawlen.", false],
    ["LEHRE & PROJEKTE (PROFESSOR:INNEN)", "Als Professor:in möchte ich Modulhandbücher anderer Hochschulen vergleichen, um Lehrmaterial und Projekte an realen Curricula auszurichten.", false],
    ["STUDIENGANGSENTWICKLUNG (FH WEDEL)", "Als Mitarbeiter der FH Wedel möchte ich neue Studiengänge mit denen anderer Hochschulen vergleichen, um fundiert zu entscheiden.", false],
    ["NEU: BACHELORARBEIT EINGEREICHT", "Als Bachelorstudent möchte ich die Plattform erweitern und die KI-Richtlinien der Hochschulen erheben – ohne einen neuen Crawler zu bauen.", true],
  ];
  cards.forEach((c, i) => {
    const x = xs[i % 2], y = ys[Math.floor(i / 2)];
    box(s, x, y, cw, ch, C.background2, "Story " + (i + 1));
    T(s, c[0], { x: x + 0.3, y: y + 0.22, w: cw - 0.6, h: 0.35, fontSize: 14, bold: true, color: c[2] ? C.accent2 : C.accent1 });
    T(s, c[1], { x: x + 0.3, y: y + 0.7, w: cw - 0.6, h: 1.35, fontSize: 17 });
  });
  T(s, "Gemeinsamer Nenner: eine zentrale, geprüfte Datenbasis – und eine Plattform, die sich auf neue Dokumenttypen erweitern lässt.", { x: X0, y: 6.4, w: CW, h: 0.45, fontSize: 16, bold: true, color: C.text2 });
}

// ================================================================ 4 Ergebnis auf einen Blick
{
  const s = content("Das Ergebnis auf einen Blick",
    "[0:45] Die Zahlen nicht vorlesen, sondern einordnen. Selbstbewusst: 'Das ist das, was in diesem Semester entstanden ist.'\n" +
    "404 Hochschulen wurden bearbeitet, 164.396 PDFs gesammelt (154 GB). In der Endliste stehen 19.049 Dokumente, davon sind geschätzt rund 18.600 echte Modulhandbücher. Bei 255 von 404 Hochschulen (63 %) gibt es mindestens ein bestätigtes Modulhandbuch.\n" +
    "Die Trefferquote von ca. 98 % ist gemessen am Urteil des Sprachmodells – das sagen wir offen dazu (Details auf Folie 'Modellqualität').\n" +
    "Die gesamten Cloud-Kosten betrugen 155 $ – das sind weniger als 1 Cent pro gefundenem Modulhandbuch (Details später).");
  const tw = 3.85, th = 2.15, xs = [0.6, 4.74, 8.88], ys = [1.55, 3.95];
  const tiles = [
    ["404", "Hochschulen bearbeitet – Universitäten, FH/HAW, Kunst- und Verwaltungshochschulen"],
    ["164.396", "PDFs gesammelt (154 GB Daten)"],
    ["≈ 18.600", "Modulhandbücher in der Endliste (19.049 Dokumente gelistet)*"],
    ["63 %", "der Hochschulen mit mindestens einem bestätigten Modulhandbuch (255 von 404)"],
    ["≈ 98 %", "geschätzte Precision (Trefferquote) der Endliste*"],
    ["155 $", "Cloud-Kosten insgesamt – weniger als 1 Cent pro Modulhandbuch"],
  ];
  tiles.forEach((t, i) => {
    const x = xs[i % 3], y = ys[Math.floor(i / 3)];
    box(s, x, y, tw, th, C.background2, "Kennzahl " + (i + 1));
    T(s, t[0], { x: x + 0.3, y: y + 0.2, w: tw - 0.6, h: 0.9, fontSize: 44, bold: true, color: C.accent1, valign: "middle" });
    T(s, t[1], { x: x + 0.3, y: y + 1.15, w: tw - 0.6, h: 0.9, fontSize: 15 });
  });
  T(s, "* Geschätzt, gemessen am Urteil des Sprachmodells (Stichprobe). Cloud-Kosten Juli bis Oktober 2026 inklusive Entwicklung, Tests und Webapp-Betrieb.", { x: X0, y: 6.4, w: CW, h: 0.4, fontSize: 12, color: C.accent4 });
}

// ================================================================ 5 Prozess
{
  const s = content("So funktioniert es: von der Hochschulliste zur geprüften Datei",
    "[1:30] Fünf Schritte, keine Technik-Details.\n" +
    "1. Eine CSV mit den Webseiten der Hochschulen genügt.\n" +
    "2. Der Crawler – ein Programm, das Webseiten wie ein Besucher durchläuft, Links folgt und PDFs lädt. Er hält sich an die Regeln der Webseiten (robots.txt) und lädt nicht mehrfach.\n" +
    "3. Ein schnelles Machine-Learning-Modell (TF-IDF mit logistischer Regression) vergibt einen Score zwischen 0 und 1: Wie sehr ähnelt dieser Text einem Modulhandbuch?\n" +
    "4. Nur für die unsichere Grauzone fragen wir ein KI-Sprachmodell (Claude Haiku 4.5), das ein Urteil mit Begründung liefert.\n" +
    "5. Ergebnis sind Dateien mit Score, Quelle und Begründung – ein Mensch kann jede Entscheidung nachvollziehen und korrigieren.\n" +
    "Kernbotschaft: Sammeln ist einfach, Aussortieren ist schwer. Deshalb arbeiten zwei Stufen zusammen – billig und schnell für die Masse, gründlich für die Grauzone.");
  const bw = 2.2, step = 2.48, y = 1.55, bh = 3.0;
  const steps = [
    ["1", "Hochschulliste", "Eine CSV mit den Webseiten der Hochschulen genügt.", "404", "Hochschulen"],
    ["2", "Crawler", "Programm, das Webseiten wie ein Besucher durchläuft, Links folgt und PDFs lädt.", "164.396", "PDFs geladen"],
    ["3", "ML-Modell", "Schnelle Vorsortierung: Wie ähnlich ist der Text einem Modulhandbuch? (Score 0–1)", "44.437", "Kandidaten"],
    ["4", "KI-Sprachmodell", "Prüft nur die unsichere Grauzone und begründet jedes Urteil.", "34.141", "geprüfte Dokumente"],
    ["5", "Ergebnis", "Dateien mit Score, Quelle und Begründung – ein Mensch kann nachprüfen.", "19.049", "in der Endliste"],
  ];
  steps.forEach((st, i) => {
    const x = X0 + i * step;
    box(s, x, y, bw, bh, i === 3 ? C.accent5 : C.background2, "Schritt " + st[0]);
    T(s, "SCHRITT " + st[0], { x: x + 0.2, y: y + 0.2, w: bw - 0.4, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
    T(s, st[1], { x: x + 0.2, y: y + 0.55, w: bw - 0.4, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    T(s, st[2], { x: x + 0.2, y: y + 1.1, w: bw - 0.4, h: 1.8, fontSize: 14 });
    T(s, st[3], { x: x, y: 4.75, w: bw, h: 0.55, fontSize: 28, bold: true, color: C.accent1, align: "center" });
    T(s, st[4], { x: x, y: 5.3, w: bw, h: 0.3, fontSize: 13, color: C.accent4, align: "center" });
    if (i < 4) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.02, y: y + 1.2, w: 0.24, h: 0.4, fill: { color: C.accent4 }, line: { color: C.accent4, width: 0 }, objectName: "Pfeil" });
  });
  T(s, "Sammeln ist einfach, Aussortieren ist schwer: Zwei Stufen teilen sich die Arbeit – schnell und günstig für die Masse, gründlich für die Grauzone.", { x: X0, y: 6.0, w: CW, h: 0.7, fontSize: 18, bold: true, color: C.text2 });
}

// ================================================================ 6 Architektur vereinfacht
{
  const s = content("Die Architektur in einem Bild",
    "[1:20] Bewusst stark vereinfacht – die vollständige Architektur liegt im Projektbericht und im Backup.\n" +
    "Zuerst AWS erklären: Amazon Web Services ist eine Cloud-Plattform, bei der man Rechenleistung und Speicher bei Bedarf mietet, statt eigene Server zu betreiben.\n" +
    "Von links nach rechts: Nutzer arbeiten im Browser. Die Webapp – Frontend (Oberfläche) und Backend (Steuerung) – nimmt Aufträge an und startet Crawl-Jobs. Die laufen auf Fargate bzw. Lambda, also nur dann, wenn sie gebraucht werden, und viele Hochschulen parallel. Die Jobs legen Dateien im Speicher ab (S3); eine Tabelle (DynamoDB) merkt sich, welche Seiten schon besucht wurden. Das Sprachmodell läuft als Cloud-Dienst (Bedrock) und prüft die Grauzone.\n" +
    "Die zentrale Entscheidung: Steuerung und Last sind getrennt. Die kleine Webapp läuft immer, die schwere Arbeit nur bei Bedarf. Deshalb skaliert das System auf 404 Hochschulen, ohne dass wir Server verwalten.");
  T(s, [
    { text: "AWS (Amazon Web Services) ", options: { bold: true } },
    { text: "= Cloud-Plattform: Rechenleistung und Speicher werden bei Bedarf gemietet, statt eigene Server zu betreiben." },
  ], { x: X0, y: 1.45, w: CW, h: 0.55, fontSize: 15, color: C.accent4 });
  const bw = 2.6, xs = [0.6, 3.77, 6.94, 10.11], y1 = 2.2, h1 = 2.0, y2 = 4.55, h2 = 1.75;
  const mk = (x, y, h, head, desc, fill, white) => {
    box(s, x, y, bw, h, fill, head);
    T(s, head, { x: x + 0.2, y: y + 0.18, w: bw - 0.4, h: 0.4, fontSize: 17, bold: true, color: white ? C.background1 : C.text2 });
    T(s, desc, { x: x + 0.2, y: y + 0.65, w: bw - 0.4, h: h - 0.75, fontSize: 14, color: white ? C.background1 : C.text1 });
  };
  mk(xs[0], y1, h1, "Nutzer im Browser", "Hochschulliste hochladen, Ergebnisse ansehen und prüfen", C.background2);
  mk(xs[1], y1, h1, "Webapp", "Frontend (Oberfläche) und Backend (Steuerung, Login, Aufträge)", C.accent1, true);
  mk(xs[2], y1, h1, "Crawl-Jobs", "AWS Fargate / Lambda: Rechenleistung nur bei Bedarf, viele Hochschulen parallel", C.background2);
  mk(xs[2], y2, h2, "KI-Prüfung", "AWS Bedrock: Sprachmodell als Cloud-Dienst", C.background2);
  // Speicher-Container
  box(s, xs[3], y1, bw, 4.1, C.accent5, "Speicher");
  T(s, "Speicher", { x: xs[3] + 0.2, y: y1 + 0.15, w: bw - 0.4, h: 0.4, fontSize: 17, bold: true, color: C.text2 });
  box(s, xs[3] + 0.2, y1 + 0.65, bw - 0.4, 1.55, C.background1, "S3");
  T(s, [{ text: "S3", options: { bold: true, breakLine: true, fontSize: 16 } }, { text: "Dateispeicher für PDFs und Ergebnisse (154 GB)", options: {} }], { x: xs[3] + 0.35, y: y1 + 0.78, w: bw - 0.7, h: 1.35, fontSize: 14 });
  box(s, xs[3] + 0.2, y1 + 2.4, bw - 0.4, 1.5, C.background1, "DynamoDB");
  T(s, [{ text: "DynamoDB", options: { bold: true, breakLine: true, fontSize: 16 } }, { text: "Merkzettel: Welche Seiten waren schon dran?", options: {} }], { x: xs[3] + 0.35, y: y1 + 2.53, w: bw - 0.7, h: 1.3, fontSize: 14 });
  arrowH(s, 3.25, y1 + 1.0, 0.47);
  arrowH(s, 6.42, y1 + 1.0, 0.47);
  arrowH(s, 9.59, y1 + 1.0, 0.47);
  arrowH(s, 9.59, y2 + 0.85, 0.47);
  // Ablauf
  box(s, 0.6, y2, 5.8, h2, C.background2, "Ablauf");
  T(s, [
    { text: "So läuft ein Auftrag", options: { bold: true, breakLine: true, color: C.text2, fontSize: 16 } },
    { text: "1  Liste hochladen, Auftrag starten", options: { breakLine: true } },
    { text: "2  Webapp startet die Crawl-Jobs", options: { breakLine: true } },
    { text: "3  Jobs legen PDFs im Speicher ab", options: { breakLine: true } },
    { text: "4  Sprachmodell prüft die Grauzone", options: { breakLine: true } },
    { text: "5  Ergebnisse erscheinen in der Webapp", options: {} },
  ], { x: 0.8, y: y2 + 0.15, w: 5.4, h: h2 - 0.25, fontSize: 14, paraSpaceAfter: 2 });
  T(s, "Steuerung und Last sind getrennt: Die kleine Webapp läuft immer, die schwere Arbeit nur bei Bedarf.", { x: X0, y: 6.55, w: 11.4, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
}

// ================================================================ 7 Funktionsumfang
{
  const s = content("Was bereits gebaut ist: der Funktionsumfang",
    "[1:30] Hier darfst du stolz sein – der Arbeitsumfang soll nicht erst im Projektbericht sichtbar werden.\n" +
    "Erheben: Massenimport per CSV, ein fokussierter Crawler (hält robots.txt ein, nutzt Sitemaps und Fakultäts-Subdomains, sucht Best-First), zusätzliche Suche über Common Crawl, Serper und Firecrawl für Hochschulen ohne Treffer, OCR für gescannte PDFs, Duplikaterkennung.\n" +
    "Prüfen: ML-Klassifikator, Sprachmodell-Zweitstufe, Review-Oberfläche mit Nachtraining (Human-in-the-Loop), Evaluationsmodul mit HTML-Bericht und Diagnose je Hochschule.\n" +
    "Betreiben: Weboberfläche mit Login, Rollen und Modellverwaltung; austauschbare Extraktionsprofile; automatisches Deployment; kompletter Neuaufbau der Cloud-Umgebung per Skript.\n" +
    "Satz zum Mitnehmen: 'Ein neuer Dokumenttyp bedeutet ein neues Profil – nicht einen neuen Crawler.'");
  const cols = [
    ["Erheben", ["Massenimport per CSV (404 Hochschulen)", "Fokussierter Crawler: robots.txt, Sitemaps, Fakultäts-Subdomains", "Zusatzsuche: Common Crawl, Serper, Firecrawl", "OCR für gescannte PDFs", "Duplikaterkennung"]],
    ["Prüfen", ["ML-Klassifikator (TF-IDF + logistische Regression)", "Sprachmodell-Zweitstufe (Claude Haiku 4.5)", "Review-Oberfläche mit Nachtraining (Human-in-the-Loop)", "Evaluationsmodul mit HTML-Bericht und Diagnose je Hochschule"]],
    ["Betreiben", ["Weboberfläche mit Login, Rollen, Modellverwaltung", "Austauschbare Extraktionsprofile", "Automatisches Deployment (CI/CD)", "Cloud-Umgebung per Skript komplett neu aufbaubar"]],
  ];
  const cw = 3.9, step = 4.115;
  cols.forEach((c, i) => {
    const x = X0 + i * step;
    box(s, x, 1.55, cw, 0.6, C.accent1, "Kopf " + c[0]);
    T(s, c[0], { x: x + 0.25, y: 1.55, w: cw - 0.5, h: 0.6, fontSize: 20, bold: true, color: C.background1, valign: "middle" });
    box(s, x, 2.15, cw, 4.1, C.background2, "Liste " + c[0]);
    T(s, bullets(c[1]), { x: x + 0.25, y: 2.35, w: cw - 0.5, h: 3.8, fontSize: 17, paraSpaceAfter: 12 });
  });
  T(s, "Ein neuer Dokumenttyp bedeutet ein neues Profil – nicht einen neuen Crawler.", { x: X0, y: 6.45, w: CW, h: 0.4, fontSize: 17, bold: true, color: C.text2 });
}

// ================================================================ 8 Herausforderungen
{
  const s = content("Herausforderungen und die Entscheidungen dahinter",
    "[1:30] Zeigen, welche technischen Probleme gelöst wurden und warum.\n" +
    "Wichtigste Erkenntnis: Das ML-Modell war im Training sehr gut (96,5 % Precision), im echten Crawl aber nur bei 25 % (Score 0,5–0,9) bzw. 82,5 % (Score ≥ 0,9). Der Grund: Prüfungsordnungen, Einzelmodulblätter und Studienverlaufspläne sehen Modulhandbüchern täuschend ähnlich. Deshalb haben wir die zweite Stufe mit Sprachmodell eingebaut – das war die Entscheidung mit der größten Wirkung.\n" +
    "Weitere Punkte kurz: Parallele Cloud-Jobs statt eigener Server; Zusatzsuche für Hochschulen ohne Treffer (bei drei Test-Hochschulen mit vorher null Treffern wurden gezielt 13 Handbücher gefunden); OCR für Scans (hoher Aufwand, kleiner Ertrag – das sagen wir offen); die befristete Cloud-Umgebung, die komplett gelöscht wird – wir haben sie per Skript in einem Lauf wiederherstellbar gemacht.");
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 15, valign: "middle" } });
  const c = (t, b) => ({ text: t, options: { fontSize: 14, valign: "middle", bold: !!b } });
  const rows = [
    [hdr("Herausforderung"), hdr("Entscheidung"), hdr("Wirkung")],
    [c("Modell im Training sehr gut (96,5 %), im echten Crawl schwach (25–82 %)", true), c("Zwei Stufen: ML-Modell für die Masse, Sprachmodell für die Grauzone"), c("Precision der Endliste ≈ 98 %")],
    [c("164.396 PDFs in vertretbarer Zeit sammeln", true), c("Parallele Cloud-Jobs statt eigener Server"), c("10–14 Tsd. PDFs pro Stunde")],
    [c("Kleine und private Hochschulen liefern nichts", true), c("Zusatzsuche über Common Crawl und Serper"), c("13 Handbücher bei 3 Test-Hochschulen mit zuvor 0 Treffern")],
    [c("Gescannte PDFs ohne Text", true), c("OCR-Nachbearbeitung"), c("3.553 Scans bearbeitet, 42 zusätzliche Treffer")],
    [c("Befristete Cloud-Umgebung wird gelöscht", true), c("Kompletter Aufbau per Skript"), c("Plattform in einem Lauf wiederherstellbar")],
  ];
  s.addTable(rows, { x: X0, y: 1.55, w: CW, colW: [4.4, 4.2, 3.53], rowH: [0.5, 0.88, 0.8, 0.8, 0.8, 0.8], border: { type: "solid", pt: 0.75, color: "D5DBE3" }, margin: [0.05, 0.12, 0.05, 0.12], objectName: "Tabelle Herausforderungen" });
}

// ================================================================ 9 Plattform in Aktion
{
  const s = content("Die Plattform in Aktion",
    "[1:30] Ankündigung selbstbewusst: 'Wir zeigen Ihnen jetzt den typischen Ablauf. Das Setup wurde vorab getestet; zur Sicherheit zeigen wir die Ansichten als Screenshots.'\n" +
    "Falls eine Live-Demo gewünscht ist: Die drei Schritte hier sind die Reihenfolge der Demo. Bei Problemen einfach souverän mit den Screenshots weitermachen: 'So sieht das normalerweise aus.'\n" +
    "1. Auftrag starten: CSV hochladen, Modell wählen, Lauf starten.\n" +
    "2. Ergebnisse: gefundene Dokumente je Hochschule mit Score und Quelle.\n" +
    "3. Prüfband: Der Mensch entscheidet nur die unsichere Grauzone – sein Urteil fließt ins Nachtraining.\n" +
    "VOR DEM VORTRAG: Screenshots (oder ein kurzes Video) einfügen und lokal gespeicherte Beispielergebnisse bereithalten.");
  const labels = [
    ["1 · Auftrag starten", "CSV mit Hochschulen hochladen, Modell wählen, Lauf starten"],
    ["2 · Ergebnisse", "Gefundene Dokumente je Hochschule mit Score und Quelle"],
    ["3 · Prüfband", "Mensch entscheidet nur die Grauzone; sein Urteil fließt ins Nachtraining"],
  ];
  labels.forEach((l, i) => {
    const x = X0 + i * 4.14;
    box(s, x, 1.55, 3.85, 3.5, C.background2, "Screenshot " + (i + 1), { line: { color: H.accent4, width: 1.25, dashType: "dash" } });
    T(s, "Screenshot einfügen", { x, y: 1.55, w: 3.85, h: 3.5, fontSize: 16, color: C.accent4, align: "center", valign: "middle" });
    T(s, l[0], { x, y: 5.25, w: 3.85, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
    T(s, l[1], { x, y: 5.7, w: 3.85, h: 0.8, fontSize: 14 });
  });
}

// ================================================================ 10 Trichter
{
  const s = content("Ergebnis: Nur etwa jedes neunte PDF ist ein Modulhandbuch",
    "[1:30] Der Trichter zeigt, wo die eigentliche Arbeit liegt.\n" +
    "Gesammelt wurden 164.396 PDFs. Das ML-Modell hat 44.437 als Kandidaten markiert. Nach der Prüfung durch das Sprachmodell und dem gezielten Nachprüfen verdächtiger Quellen stehen 19.049 Dokumente in der Endliste, davon sind geschätzt rund 18.600 echte Modulhandbücher.\n" +
    "Zwei Listen nennen: 'streng' (nur vom Sprachmodell bestätigt) mit 11.771 Dokumenten und 'erweitert' mit 19.049 Dokumenten inklusive der Dokumente mit sehr hohem Score.\n" +
    "Botschaft: Das Herunterladen ist nicht der Engpass. Der Engpass ist die Entscheidung, ob ein 90-seitiges PDF wirklich ein Modulhandbuch ist.");
  T(s, "Vom Crawl zur Endliste (Anzahl Dokumente)", { x: X0, y: 1.5, w: 7.6, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{
    name: "Dokumente",
    labels: ["Gesammelte PDFs", "Kandidaten des ML-Modells", "Endliste (erweitert)", "davon echt (geschätzt)"],
    values: [164396, 44437, 19049, 18628],
  }], chartBase({ x: X0, y: 1.95, w: 7.7, h: 4.3, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, chartColors: [H.accent4, H.accent5, H.accent1, H.accent3], dataLabelFormatCode: "#,##0", dataLabelPosition: "outEnd", barGapWidthPct: 40, catAxisLabelFontSize: 14, dataLabelFontSize: 14, valAxisMaxVal: 190000 }));
  box(s, 8.9, 1.55, 3.83, 4.7, C.background2, "Aussage");
  T(s, "1 von 9", { x: 9.15, y: 1.8, w: 3.4, h: 0.9, fontSize: 48, bold: true, color: C.accent1 });
  T(s, "gesammelten PDFs ist ein Modulhandbuch.", { x: 9.15, y: 2.75, w: 3.4, h: 0.7, fontSize: 17, bold: true, color: C.text2 });
  T(s, bullets(["Sammeln ist nicht der Engpass, Aussortieren ist es.", "Streng (nur vom Sprachmodell bestätigt): 11.771", "Erweitert (zusätzlich Score ≥ 0,9): 19.049"]), { x: 9.15, y: 3.65, w: 3.4, h: 2.5, fontSize: 14, paraSpaceAfter: 8 });
}

// ================================================================ 11 Modellqualität
{
  const s = content("Warum die zweite Stufe nötig war: Training ist nicht Praxis",
    "[1:30] Das ist das wichtigste inhaltliche Ergebnis – und es ist ein Erfolg der Methodik, nicht ein Eingeständnis.\n" +
    "Im Training erreicht das ML-Modell eine Precision von 96,5 % (Kreuzvalidierung, gruppiert nach Hochschule). Im echten Crawl liegt sie nur bei 25 % für Scores zwischen 0,5 und 0,9 und bei 82,5 % für Scores ab 0,9. Grund: Das Trainingsset (2.695 Dokumente von 269 Hochschulen) enthält nicht die ganze Breite an Beinahe-Treffern im Web.\n" +
    "Die Fehlerarten: Die Hälfte der falschen Treffer sind Prüfungs- oder Studienordnungen, ein Fünftel Einzelmodulblätter, 10 % Studienverlaufspläne.\n" +
    "Dank der Sprachmodell-Stufe und der gezielten Nachprüfung verdächtiger Quellen steigt die geschätzte Precision der Endliste auf ca. 98 %.\n" +
    "Ehrlichkeit als Stärke: Die Referenz ist das Urteil des Sprachmodells. Eine manuelle Stichprobe von 20 Dokumenten ergab 85 % Übereinstimmung. Wir haben außerdem einen Fehler in der eigenen Auswertung gefunden und korrigiert – das stärkt die Aussagekraft.");
  T(s, "Precision (Anteil richtiger Treffer) in Prozent", { x: X0, y: 1.5, w: 7.4, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{
    name: "Precision",
    labels: ["Training (Kreuzvalidierung)", "Praxis: Score 0,5–0,9", "Praxis: Score ≥ 0,9", "Endliste nach Sprachmodell"],
    values: [96.5, 25, 82.5, 98],
  }], chartBase({ x: X0, y: 1.95, w: 7.5, h: 4.3, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 115, chartColors: [H.accent4, H.accent2, H.accent2, H.accent3], dataLabelFormatCode: '0.0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 50, catAxisLabelFontSize: 12, dataLabelFontSize: 15 }));
  box(s, 8.4, 1.55, 4.33, 4.7, C.background2, "Erklärung");
  T(s, "Was dahinter steckt", { x: 8.65, y: 1.75, w: 3.85, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  T(s, bullets([
    "Beinahe-Treffer täuschen das Modell: Hälfte der falschen Treffer sind Prüfungsordnungen, ein Fünftel Einzelmodulblätter.",
    "Training: 2.695 Dokumente von 269 Hochschulen – zu wenig Breite.",
    "Darum: Sprachmodell prüft die Grauzone.",
    "Referenz ist das Sprachmodell; manuelle Stichprobe (20 Dokumente): 85 % Übereinstimmung.",
  ]), { x: 8.65, y: 2.3, w: 3.85, h: 3.85, fontSize: 14, paraSpaceAfter: 8 });
}

// ================================================================ 12 Abdeckung
{
  const s = content("Abdeckung: 63 % der Hochschulen – große öffentliche fast vollständig",
    "[1:30] Unterschiede zwischen Hochschulen sind selbst schon ein Ergebnis.\n" +
    "Links nach Trägerschaft: öffentlich-rechtliche Hochschulen sind zu 78 % abgedeckt, kirchliche zu 51 %, private nur zu 39 %. Rechts nach Größe (Studierendenzahl): Bei Hochschulen mit 15.000 bis 30.000 Studierenden sind es 97 %, bei Hochschulen unter 1.000 Studierenden nur 44 %.\n" +
    "Ursachen: Kleine und private Seiten haben kaum PDFs, Handbücher hinter Login oder in JavaScript-Portalen. Das sind genau die Lücken, an denen die Zusatzsuche und die Seitenebenen-Klassifikation ansetzen (Ausblick).\n" +
    "Nach Typ (Backup): Universitäten 76 %, Künstlerische Hochschulen 70 %, FH/HAW 60 %, Verwaltungshochschulen 44 %. 39 Hochschulen ohne jeden Fund.");
  T(s, "Nach Trägerschaft (Anteil Hochschulen mit ≥ 1 Modulhandbuch)", { x: X0, y: 1.5, w: 5.9, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: "Abdeckung", labels: ["öffentlich-rechtlich (258)", "kirchlich (37)", "privat (108)"], values: [78, 51, 39] }],
    chartBase({ x: X0, y: 1.95, w: 5.9, h: 3.7, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 110, chartColors: [H.accent1], dataLabelFormatCode: '0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 60, dataLabelFontSize: 15 }));
  T(s, "Nach Größe (Studierende; Anzahl Hochschulen)", { x: 6.83, y: 1.5, w: 5.9, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: "Abdeckung", labels: ["< 1.000 (146)", "1–5 Tsd. (113)", "5–15 Tsd. (87)", "15–30 Tsd. (36)", "> 30 Tsd. (18)"], values: [44, 70, 79, 97, 78] }],
    chartBase({ x: 6.83, y: 1.95, w: 5.9, h: 3.7, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 110, chartColors: [H.accent1], dataLabelFormatCode: '0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 60, dataLabelFontSize: 15, catAxisLabelFontSize: 11 }));
  box(s, X0, 5.85, CW, 0.85, C.background2, "Fazit Abdeckung");
  T(s, "Lücken liegen bei kleinen, privaten Hochschulen: kaum PDFs, Login-Bereiche, JavaScript-Portale. 39 Hochschulen blieben ganz ohne Fund.", { x: X0 + 0.3, y: 5.85, w: CW - 0.6, h: 0.85, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
}

// ================================================================ 13 Daten & Fakten
{
  const s = content("Daten und Fakten: Laufzeit, Umfang, Aktualität",
    "[1:30] Hier die Zahlen, die der Zuhörer als Forschungsdaten einordnen kann.\n" +
    "Laufzeit: Der erste Großlauf über 411 Hochschulen dauerte 6,3 Stunden, der Deep Run knapp 13 Stunden und holte 132.187 PDFs. Spitzendurchsatz: 10.000–14.000 neue PDFs pro Stunde.\n" +
    "Datenmenge: 154 GB in rund 193.000 Dateien. Duplikate: 14 % der Endliste (2.733 von 19.049) haben denselben Host und Dateinamen.\n" +
    "Manueller Aufwand: Ohne das Sprachmodell hätten 34.141 Dokumente der Grauzone von Hand geprüft werden müssen – bei 30 Sekunden je Dokument rund 285 Stunden (Modellrechnung, keine Messung). Nicht entscheidbar blieben 1.658 Dokumente.\n" +
    "Aktualität (Diagramm): Bei 11.758 Dokumenten steht eine Jahreszahl im Dateinamen; zwei Drittel stammen aus 2020 oder später, die ältesten ab 2001.\n" +
    "Konzentration: Die zehn ergiebigsten Hochschulen liefern 40 % aller Funde; die mediane Hochschule hat 4 Modulhandbücher.");
  T(s, "Aktualität: Jahr im Dateinamen (11.758 Dokumente)", { x: X0, y: 1.5, w: 6.3, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  const yl = ["bis 2014", "2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"];
  const yv = [1807, 491, 280, 398, 430, 529, 1365, 765, 732, 1233, 1079, 1183, 1451];
  s.addChart(pres.charts.BAR, [{ name: "Dokumente", labels: yl, values: yv }],
    chartBase({ x: X0, y: 1.95, w: 6.3, h: 3.9, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, chartColors: [H.accent1], dataLabelFormatCode: "#,##0", dataLabelPosition: "outEnd", barGapWidthPct: 35, catAxisLabelFontSize: 11, dataLabelFontSize: 11 }));
  T(s, "Zwei Drittel der datierbaren Dokumente stammen aus 2020 oder später; die ältesten ab 2001.", { x: X0, y: 5.95, w: 6.3, h: 0.7, fontSize: 14, color: C.accent4 });
  const tiles = [
    ["6,3 h / 13 h", "Laufzeit: Erstlauf (411 Hochschulen) / Deep Run (132 Tsd. PDFs)"],
    ["10–14 Tsd.", "neue PDFs pro Stunde im Spitzenbereich"],
    ["154 GB", "gespeicherte Daten in rund 193 Tsd. Dateien"],
    ["14 %", "Duplikate in der Endliste (2.733 von 19.049)"],
    ["≈ 285 h", "Handprüfung gespart (34.141 Dokumente × 30 s, Modellrechnung)"],
    ["40 %", "aller Funde stammen von den 10 ergiebigsten Hochschulen"],
  ];
  const tw = 2.68, th = 1.5, txs = [7.2, 10.05], tys = [1.55, 3.2, 4.85];
  tiles.forEach((t, i) => {
    const x = txs[i % 2], y = tys[Math.floor(i / 2)];
    box(s, x, y, tw, th, C.background2, "Fakt " + (i + 1));
    T(s, t[0], { x: x + 0.15, y: y + 0.1, w: tw - 0.3, h: 0.55, fontSize: 24, bold: true, color: C.accent1, valign: "middle" });
    T(s, t[1], { x: x + 0.15, y: y + 0.7, w: tw - 0.3, h: 0.75, fontSize: 12 });
  });
}

// ================================================================ 14 Kosten & Hochrechnung
{
  const s = content("Kosten: 155 $ insgesamt – und eine Vollerhebung bleibt bezahlbar",
    "[2:00] Kosten transparent zeigen – das ist ein Argument für Skalierbarkeit.\n" +
    "Gesamtkosten Juli bis 5. Oktober 2026: 155,60 $ (Abrechnung der Cloud-Umgebung). 69 % davon, 107 $, entfielen auf die KI-Prüfung mit dem Sprachmodell (rund 34.000 Dokumente). Das Crawlen selbst – die Rechenzeit der beiden Großläufe – kostete nur etwa 7 $, der Speicher 6 $.\n" +
    "Überraschung: Die dauerhaft laufende Webapp (Server, feste IP-Adresse, Datenträger) kostete rund 28 $ und damit mehr als alle Crawls zusammen. Ein Betrieb nur bei Bedarf wäre günstiger.\n" +
    "Rechnerisch ergibt das weniger als 1 Cent pro gefundenem Modulhandbuch (155 $ / ca. 18.600) – wohlgemerkt inklusive Entwicklung und Tests.\n" +
    "Hochrechnung (rechte Tabelle): Für eine Vollerhebung mit 40.000 Modulhandbüchern (Fachschätzung) wären ca. 350.000 PDFs, 280 GB, rund 40 Stunden Rechenzeit und etwa 230 $ für die Prüfung nötig. Es ist eine lineare Hochrechnung; die tatsächliche Ausbeute pro PDF dürfte schlechter sein, weil die restlichen Handbücher auf schwer erreichbaren Seiten liegen.\n" +
    "Zur Skalierung: Das Limit von ca. 200 Dokumenten gilt nur für Testläufe; für die Vollerhebung ist eine umfassende rekursive Erfassung der Hochschulwebseiten vorgesehen. Im Deep Run wurden 132.187 PDFs in einem Lauf geholt.");
  T(s, "Wofür das Geld ging (Juli–Okt 2026, in US-Dollar)", { x: X0, y: 1.5, w: 6.4, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{
    name: "Kosten",
    labels: ["KI-Prüfung (Bedrock)", "Webapp-Server & Netzwerk", "Steuern", "Crawl-Rechenzeit (Fargate)", "Speicher (S3)", "Sonstiges"],
    values: [107.2, 28.1, 7.1, 7.1, 5.7, 0.3],
  }], chartBase({ x: X0, y: 1.95, w: 6.4, h: 3.9, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, chartColors: [H.accent1], dataLabelFormatCode: '0.0" $"', dataLabelPosition: "outEnd", barGapWidthPct: 40, catAxisLabelFontSize: 13, dataLabelFontSize: 13, valAxisMaxVal: 135 }));
  T(s, "Die dauerhaft laufende Webapp (28 $) kostete mehr als alle Crawls zusammen (7 $).", { x: X0, y: 5.95, w: 6.4, h: 0.7, fontSize: 14, bold: true, color: C.text2 });
  T(s, "Hochrechnung: Vollerhebung mit 40.000 Modulhandbüchern", { x: 7.3, y: 1.5, w: 5.43, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  const hh = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 14, valign: "middle" } });
  const cc = (t, b) => ({ text: t, options: { fontSize: 14, valign: "middle", bold: !!b } });
  s.addTable([
    [hh(""), hh("Ist"), hh("Vollerhebung")],
    [cc("PDFs", true), cc("164 Tsd."), cc("≈ 350 Tsd.")],
    [cc("Speicher", true), cc("154 GB"), cc("≈ 280 GB")],
    [cc("Crawl-Zeit", true), cc("≈ 19 h"), cc("≈ 40 h")],
    [cc("KI-Prüfung", true), cc("107 $"), cc("≈ 230 $")],
  ], { x: 7.3, y: 1.95, w: 5.43, colW: [1.7, 1.55, 2.18], rowH: 0.55, border: { type: "solid", pt: 0.75, color: "D5DBE3" }, margin: [0.04, 0.12, 0.04, 0.12], objectName: "Tabelle Hochrechnung" });
  T(s, "Lineare Hochrechnung bei gleicher Ausbeute (8,8 PDFs je Modulhandbuch; Zielwert 40.000 laut Fachschätzung). Testläufe nutzen ein Limit (ca. 200 Dokumente); der Deep Run holte 132.187 PDFs in einem Lauf. Die reale Ausbeute dürfte schlechter sein.", { x: 7.3, y: 5.85, w: 5.43, h: 1.0, fontSize: 12, color: C.accent4 });
  T(s, [{ text: "Vollerhebung ", options: { bold: true } }, { text: "= alle Modulhandbücher aller deutschen Hochschulen erfassen (Fachschätzung: ca. 40.000)." }], { x: 7.3, y: 4.85, w: 5.43, h: 0.9, fontSize: 14, color: C.text2 });
}

// ================================================================ 15 Forschungspotenzial
{
  const s = content("Forschungspotenzial: Was der Datensatz beantworten kann",
    "[1:30] Der Forschungsaspekt wird stärker betont, wie im Feedback gefordert.\n" +
    "Links die Fragen, die mit diesem Datensatz erstmals systematisch untersuchbar sind: Unterschiede zwischen Hochschulen, Aktualisierungshäufigkeit, zentrale vs. dezentrale Bereitstellung, kleine vs. große Hochschulen, gemeinsame Strukturen von Studiengängen, und wie vollständig sich Hochschulwebseiten automatisiert erfassen lassen.\n" +
    "Rechts erste Befunde, die schon jetzt sichtbar sind: Die Uni Augsburg stellt über ein einziges Portal 1.801 Dokumente bereit, die mediane Hochschule hat 4 – zentral vs. dezentral. Kleine Hochschulen (<1.000 Studierende) haben im Schnitt 6 Handbücher, Hochschulen mit 15.000–30.000 Studierenden im Schnitt 222. Zwei Drittel der datierbaren Dokumente sind ab 2020. Öffentlich-rechtliche Hochschulen sind zu 78 % abgedeckt, private zu 39 %.\n" +
    "Einbettung: Forschungsgruppe KIWIT (BMFTR-gefördert), Forschungsprofil A – Erhebung öffentlich zugänglicher Hochschulinformationen. Nächster Anwendungsfall ist die Erhebung von KI-Richtlinien der Hochschulen.");
  box(s, X0, 1.55, 5.9, 4.65, C.background2, "Fragen");
  T(s, "Fragen, die der Datensatz beantwortet", { x: X0 + 0.3, y: 1.75, w: 5.3, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  T(s, bullets([
    "Wie unterscheiden sich Modulhandbücher zwischen Hochschulen?",
    "Wie oft werden Studiengänge und Module aktualisiert?",
    "Wie zentral oder dezentral stellen Hochschulen ihre Dokumente bereit?",
    "Wie unterscheiden sich kleine und große Hochschulen?",
    "Welche Strukturen teilen Studiengänge?",
    "Wie vollständig lassen sich Hochschulwebseiten automatisiert erfassen?",
  ]), { x: X0 + 0.3, y: 2.3, w: 5.3, h: 3.8, fontSize: 16, paraSpaceAfter: 9 });
  T(s, "Erste Befunde aus den Daten", { x: 6.78, y: 1.5, w: 5.95, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  const f = [
    ["1.801", "Dokumente auf einem einzigen Portal (Uni Augsburg) – Median: 4 je Hochschule"],
    ["6 vs. 222", "Ø Handbücher: Hochschulen unter 1.000 vs. 15–30 Tsd. Studierende"],
    ["⅔", "der datierbaren Dokumente stammen aus 2020 oder später"],
    ["78 vs. 39 %", "Abdeckung: öffentlich-rechtliche vs. private Hochschulen"],
  ];
  const fx = [6.78, 9.85], fy = [2.0, 4.2];
  f.forEach((t, i) => {
    const x = fx[i % 2], y = fy[Math.floor(i / 2)];
    box(s, x, y, 2.88, 2.0, C.background2, "Befund " + (i + 1));
    T(s, t[0], { x: x + 0.2, y: y + 0.15, w: 2.5, h: 0.65, fontSize: 28, bold: true, color: C.accent1, valign: "middle" });
    T(s, t[1], { x: x + 0.2, y: y + 0.85, w: 2.5, h: 1.1, fontSize: 15 });
  });
  T(s, "Einbettung: Forschungsgruppe KIWIT (BMFTR-gefördert), Forschungsprofil A – Erhebung öffentlich zugänglicher Hochschulinformationen.", { x: X0, y: 6.45, w: 11.4, h: 0.4, fontSize: 13, color: C.accent4 });
}

// ================================================================ 16 Grenzen & Ausblick
{
  const s = content("Grenzen offen benannt – und die nächsten Schritte",
    "[1:30] Selbstbewusst und ehrlich: Wir wissen genau, wo die Lücken sind, und haben die Werkzeuge, sie zu schließen.\n" +
    "Grenzen: Der Recall ist unvollständig. Gegenüber der Fachschätzung von rund 40.000 Modulhandbüchern haben wir etwa 40 % erreicht (rund 16.300 eindeutige Dokumente in der Endliste); die 40.000 sind eine Größenordnung, keine Messung. 39 Hochschulen blieben ohne Fund, private und Verwaltungshochschulen sind schwach abgedeckt. Und: Alle Qualitätsangaben messen die Übereinstimmung mit dem Sprachmodell; die manuelle Referenz (20 Dokumente) ist klein.\n" +
    "Nächste Schritte: (1) Bachelorarbeit – KI-Richtlinien der Hochschulen mit neuem Extraktionsprofil erheben. (2) Inhaltliche Erschließung: aus 'ist ein Modulhandbuch' wird 'was steht darin' – Module, ECTS, Lernziele, Prüfungsformen. (3) Recall verbessern: JavaScript-Portale, Seitenebene statt Dateiebene, Nachtraining mit den über 34.000 Sprachmodell-Urteilen, höhere Schwelle im Live-Crawl. (4) Betrieb: Webapp nur bei Bedarf, Datensatz für Folgeprojekte bereitstellen.");
  box(s, X0, 1.55, 5.95, 0.6, C.accent2, "Kopf Grenzen");
  T(s, "Grenzen", { x: X0 + 0.25, y: 1.55, w: 5.4, h: 0.6, fontSize: 20, bold: true, color: C.background1, valign: "middle" });
  box(s, X0, 2.15, 5.95, 4.15, C.background2, "Liste Grenzen");
  T(s, bullets([
    "Recall: etwa 40 % des Erwartungswerts (≈ 16.300 von ≈ 40.000 laut Fachschätzung)",
    "39 Hochschulen ohne Fund; private und Verwaltungshochschulen schwach abgedeckt",
    "Qualität gemessen am Sprachmodell; manuelle Stichprobe klein (20 Dokumente)",
    "OCR: hoher Aufwand, kleiner Ertrag (42 zusätzliche Treffer)",
  ]), { x: X0 + 0.25, y: 2.35, w: 5.45, h: 3.85, fontSize: 17, paraSpaceAfter: 14 });
  box(s, 6.78, 1.55, 5.95, 0.6, C.accent3, "Kopf Schritte");
  T(s, "Nächste Schritte", { x: 7.03, y: 1.55, w: 5.4, h: 0.6, fontSize: 20, bold: true, color: C.background1, valign: "middle" });
  box(s, 6.78, 2.15, 5.95, 4.15, C.background2, "Liste Schritte");
  T(s, [
    { text: "Bachelorarbeit: ", options: { bold: true, bullet: true } }, { text: "KI-Richtlinien der Hochschulen mit neuem Extraktionsprofil erheben", options: { breakLine: true } },
    { text: "Inhalte erschließen: ", options: { bold: true, bullet: true } }, { text: "Module, ECTS, Lernziele und Prüfungsformen strukturiert auslesen", options: { breakLine: true } },
    { text: "Recall verbessern: ", options: { bold: true, bullet: true } }, { text: "JavaScript-Portale, Nachtraining mit 34.000 Urteilen, höhere Schwelle", options: { breakLine: true } },
    { text: "Betrieb: ", options: { bold: true, bullet: true } }, { text: "Webapp nur bei Bedarf, Datensatz für Folgeprojekte bereitstellen", options: {} },
  ], { x: 7.03, y: 2.35, w: 5.45, h: 3.85, fontSize: 17, paraSpaceAfter: 14 });
}

// ================================================================ 17 Fazit
{
  const s = content("Fazit: Aus einem Prototyp wurde eine Forschungsinfrastruktur",
    "[0:45] Drei Sätze zum Mitnehmen, dann souverän schließen.\n" +
    "1. Wir haben nicht nur ein Skript gebaut, sondern eine Plattform: 404 Hochschulen, 164.396 PDFs, rund 18.600 geprüfte Modulhandbücher.\n" +
    "2. Das zweistufige Vorgehen mit ML-Modell und Sprachmodell war der entscheidende Erkenntnisgewinn – Trainingsgüte ist nicht Praxisgüte.\n" +
    "3. Die Datengrundlage und die Plattform sind wiederverwendbar – für Forschung, Lehre und Folgeprojekte; die KI-Richtlinien der Hochschulen sind der nächste Anwendungsfall.\n" +
    "Abschluss: 'Vielen Dank. Wir freuen uns auf Ihre Fragen.' Kein 'hoffentlich war es nicht zu lang'.");
  const items = [
    ["1", "Plattform statt Skript", "404 Hochschulen, 164.396 PDFs, ≈ 18.600 geprüfte Modulhandbücher – für 155 $ Cloud-Kosten."],
    ["2", "Zwei Stufen wirken", "Training ist nicht Praxis: ML-Modell plus Sprachmodell hebt die Precision von 25–82 % auf ≈ 98 %."],
    ["3", "Wiederverwendbar", "Datenbasis und Plattform tragen Forschung, Lehre und Folgeprojekte – KI-Richtlinien sind der nächste Anwendungsfall."],
  ];
  items.forEach((it, i) => {
    const x = X0 + i * 4.14;
    box(s, x, 1.55, 3.85, 3.6, C.background2, "Fazit " + it[0]);
    T(s, it[0], { x: x + 0.3, y: 1.75, w: 1, h: 0.8, fontSize: 40, bold: true, color: C.accent1 });
    T(s, it[1], { x: x + 0.3, y: 2.65, w: 3.25, h: 0.5, fontSize: 20, bold: true, color: C.text2 });
    T(s, it[2], { x: x + 0.3, y: 3.25, w: 3.25, h: 1.8, fontSize: 17 });
  });
  T(s, "Vielen Dank – wir freuen uns auf Ihre Fragen.", { x: X0, y: 5.65, w: CW, h: 0.8, fontSize: 32, bold: true, color: C.text2, valign: "middle" });
}

// ================================================================ Backup-Trenner
{
  const s = pres.addSlide({ masterName: "TITLE" });
  s.addText("Anhang / Backup", { placeholder: "title" });
  s.addText("Gesamtarchitektur · Manifest und Metadaten · ML-Modell · Sprachmodell-Stufe · Modularität · Discovery · Recht und Betrieb · Evaluation · FAQ · Fehlerarten · Abdeckung · Kosten · Projektverlauf · Glossar", { placeholder: "body" });
  s.addNotes("Nur bei Rückfragen zeigen. Alle Folien dahinter dienen als Nachschlagewerk.");
}

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

// ---------------------------------------------------------------- Gesamtarchitektur (vereinfacht)
{
  const s = content("Backup: Gesamtarchitektur (vereinfacht)",
    "Vereinfachte Gesamtsicht – nur die Teile, die für das Verständnis nötig sind. Links die Steuerung (EC2, läuft dauerhaft): Webapp mit Login, Nutzer-/Rollen-Datenbank (SQLite) und Review-Oberfläche. In der Mitte die Last (nur bei Bedarf): Je nach Anzahl der URLs startet die Webapp Lambda (bis 10 URLs) oder Fargate (Bulk). Beide nutzen dasselbe Container-Image: Crawler mit Extraktionsprofil und ML-Klassifikation. Rechts der gemeinsame Zustand: S3 (PDFs, Manifeste, Feedback) und DynamoDB (bereits besuchte URLs). Unten rechts die Nachbearbeitung, die auf dem Laptop bzw. im Batch läuft: Sprachmodell-Prüfung (Bedrock), OCR, Auswertung und Nachtraining. Unten links CI/CD: Ein Push auf GitHub baut das Image und aktualisiert Lambda, Fargate und die Webapp. Unten Mitte die externen Quellen: Hochschulwebseiten und Discovery-Dienste.\n" +
    "Zahlen: 1 = Auftrag, 2 = Crawl und Speichern, 2 umfasst auch das Lesen der Ergebnisse durch die Webapp aus S3, 3 = Nachbearbeitung liest/schreibt S3.");
  // Lanes
  lane(s, 0.5, 1.4, 3.5, 3.6, "Steuerung · EC2 (immer an)", C.background2);
  lane(s, 4.6, 1.4, 4.0, 3.45, "Last · nur bei Bedarf (AWS)", C.background2);
  lane(s, 9.2, 1.4, 3.63, 2.65, "Zustand · geteilt", C.accent5);
  lane(s, 9.2, 4.3, 3.63, 1.8, "Nachbearbeitung · Batch", C.background2);
  // Steuerung
  node(s, 0.7, 1.9, 3.1, 0.55, "Nutzer im Browser");
  node(s, 0.7, 2.7, 3.1, 0.75, "Webapp (FastAPI)\nHTTPS über Caddy", { fill: C.accent1, color: C.background1, bold: true });
  node(s, 0.7, 3.7, 3.1, 0.55, "SQLite: Nutzer, Rollen, Modelle");
  node(s, 0.7, 4.35, 3.1, 0.55, "Review-Oberfläche", {});
  vArrow(s, 2.25, 2.45, 2.7); vArrow(s, 2.25, 3.45, 3.7);
  // Last
  node(s, 4.8, 1.9, 3.6, 0.6, "Routing nach Anzahl der URLs");
  node(s, 4.8, 2.8, 1.75, 0.8, "Lambda\n≤ 10 URLs");
  node(s, 6.65, 2.8, 1.75, 0.8, "Fargate\nBulk-Läufe");
  node(s, 4.8, 3.9, 3.6, 0.8, "Crawler (Profil) →\nML-Klassifikation", { fill: C.accent1, color: C.background1, bold: true });
  vArrow(s, 6.6, 2.5, 2.8); vArrow(s, 6.6, 3.6, 3.9);
  // Zustand
  node(s, 9.4, 1.9, 3.23, 0.9, "S3: PDFs, Manifeste,\nFeedback (154 GB)");
  node(s, 9.4, 2.95, 3.23, 0.8, "DynamoDB:\nbesuchte URLs");
  // Nachbearbeitung
  node(s, 9.4, 4.75, 3.23, 0.6, "LLM-Prüfung (Bedrock)");
  node(s, 9.4, 5.4, 3.23, 0.55, "OCR · Auswertung · Nachtraining");
  // extern
  node(s, 4.8, 5.3, 3.6, 0.8, "Hochschulwebseiten ·\nDiscovery (Serper u. a.)", { fill: C.accent4, color: C.background1, bold: true });
  vArrow(s, 6.6, 4.85, 5.3, true);
  node(s, 0.7, 5.3, 3.1, 0.8, "CI/CD: GitHub Actions →\nImage → Lambda/Fargate", { fill: C.accent4, color: C.background1, bold: true });
  // Lane-Pfeile
  arrowH(s, 4.02, 3.1, 0.56); step(s, 4.3, 2.85, 1);
  arrowH(s, 8.62, 3.1, 0.56); step(s, 8.9, 2.85, 2);
  vArrow(s, 11.0, 4.05, 4.3); step(s, 11.25, 4.17, 3);
  // Legende
  T(s, [
    { text: "1 ", options: { bold: true, color: C.accent2 } }, { text: "Auftrag starten    ", options: {} },
    { text: "2 ", options: { bold: true, color: C.accent2 } }, { text: "Crawlen, klassifizieren, speichern (Webapp liest Ergebnisse aus S3)    ", options: {} },
    { text: "3 ", options: { bold: true, color: C.accent2 } }, { text: "Prüfung und Nachtraining", options: {} },
  ], { x: X0, y: 6.4, w: CW, h: 0.4, fontSize: 14 });
  T(s, "Vereinfachte Darstellung; vollständiges Diagramm im Projektbericht, Kapitel 4.", { x: X0, y: 6.75, w: 11, h: 0.25, fontSize: 11, color: C.accent4 });
}

// ---------------------------------------------------------------- Manifest & Metadaten
{
  const s = content("Backup: Was pro Dokument gespeichert wird (Manifest und Metadaten)",
    "Jede Entscheidung des Systems ist nachvollziehbar. Für jedes heruntergeladene Dokument schreibt die Pipeline eine JSON-Zeile in das Manifest (JSONL-Datei, S3-Pfad manifests/<batch_id>.jsonl). Die Webapp findet die Ergebnisse eines Laufs über die batch_id. Gruppen: Herkunft (wo gefunden, wann), Ablage (S3-Schlüssel), ML-Stufe (Score und automatische Entscheidung), Sprachmodell-Stufe (Urteil, Konfidenz, Begründung, Modell, verwendete Spec) und Auswertung (Endstatus und Lauf). Die Verdikte aus der Review-Oberfläche liegen getrennt unter feedback/<job_id>.jsonl und sind absichtlich modell-unabhängig (positive/negative). Die Hochschul-Metadaten stammen aus der Hochschulliste (404 Einträge, u. a. Typ, Trägerschaft, Bundesland, Studierendenzahl, Gründungsjahr) und werden über die Domain den Dokumenten zugeordnet – so entstehen die Auswertungen nach Typ, Träger, Größe und Bundesland. Die Dokumente selbst liegen unter scraped/<Host>/<job_id>/<Dateiname>.");
  const rows = [
    [hc("Gruppe"), hc("Felder")],
    [tc("Herkunft", true), tc("url, source_page, hostname, filename, file_type, crawled_at, job_id")],
    [tc("Ablage", true), tc("s3_key (scraped/<Host>/<job_id>/<Datei>)")],
    [tc("ML-Stufe", true), tc("module_handbook_score, decision, is_module_handbook, extraction_status, model_version")],
    [tc("Sprachmodell", true), tc("llm_is_match, llm_confidence, llm_reason, llm_model, llm_spec")],
    [tc("Auswertung", true), tc("tier (Endstatus), source_run (Lauf)")],
  ];
  s.addTable(rows, { x: X0, y: 1.5, w: 5.9, colW: [1.6, 4.3], rowH: [0.45, 0.75, 0.6, 0.95, 0.75, 0.6], border: TB, margin: [0.04, 0.1, 0.04, 0.1], objectName: "Tabelle Manifest" });
  box(s, X0, 5.75, 5.9, 1.1, C.background2, "Hochschul-Metadaten");
  T(s, [
    { text: "Hochschul-Metadaten ", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "Name, Typ, Trägerschaft, Bundesland, Studierende, Gründungsjahr, Domain – Zuordnung über die Domain.", options: {} },
  ], { x: X0 + 0.2, y: 5.8, w: 5.5, h: 1.0, fontSize: 13, valign: "middle" });
  box(s, 6.78, 1.5, 5.95, 5.35, C.background2, "Beispiel");
  T(s, "Beispiel: ein Manifest-Eintrag (gekürzt)", { x: 7.0, y: 1.65, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  T(s, [
    "{",
    '  "url": ".../BSc_Medizinische_Informatik.pdf",',
    '  "source_page": "https://mhb.uni-augsburg.de/...",',
    '  "file_type": "pdf",',
    '  "crawled_at": "2026-09-16T14:54:20Z",',
    '  "module_handbook_score": 0.9392,',
    '  "decision": "automatic_positive",',
    '  "llm_is_match": true,',
    '  "llm_confidence": 0.98,',
    '  "llm_reason": "German university',
    '     Modulhandbuch for B.Sc. ... with',
    '     ECTS, learning outcomes, exam forms",',
    '  "llm_model": "claude-haiku-4-5",',
    '  "tier": "llm_confirmed"',
    "}",
  ].map((t, i, a) => ({ text: t, options: { breakLine: i < a.length - 1 } })), { x: 7.0, y: 2.15, w: 5.5, h: 4.6, fontSize: 12, fontFace: "Courier New", color: C.text1 });
}

// ---------------------------------------------------------------- ML-Modell: Aufbau
{
  const s = content("Backup: Das ML-Modell – wie es funktioniert",
    "Das Modell beantwortet eine Frage: Wie sehr ähnelt dieses Dokument einem Modulhandbuch? Schritte: (1) Text aus dem PDF extrahieren (bis zu 400.000 Zeichen; Scans ohne Textebene werden markiert und nie stillschweigend als negativ gewertet). (2) TF-IDF: Wörter und Wortpaare (1–2 Wörter) sowie Zeichenfolgen (3–5 Zeichen, robust gegen OCR-Fehler und Silbentrennung) werden in Zahlen umgewandelt; Wörter, die in diesem Dokument häufig, insgesamt aber selten sind, zählen viel – zum Beispiel 'Lernergebnisse', 'ECTS', 'Prüfungsform'. Je bis zu 60.000 Merkmale. (3) Logistische Regression mit ausgeglichenen Klassengewichten: ein lineares, schnelles und interpretierbares Modell. (4) Der Score zwischen 0 und 1 wird in drei Klassen übersetzt: unten automatisch negativ, oben automatisch positiv, dazwischen unsicher (Review bzw. Sprachmodell). Die Schwellen werden aus den Trainingsdaten abgeleitet, nicht fest auf 0,5 gesetzt. Bewusst kein Transformer: Das Modell verarbeitet 165.000 PDFs in Stunden auf normaler CPU, ist erklärbar und ehrlich evaluierbar. Der Engpass war die Breite der Trainingsdaten, nicht die Modellgröße.");
  const steps = [
    ["1 · Text", "PDF → Text (bis 400.000 Zeichen). Scans werden markiert, nie still als negativ gewertet."],
    ["2 · TF-IDF", "Wörter (1–2) und Zeichenfolgen (3–5) werden zu Zahlen; seltene, aber typische Wörter zählen viel."],
    ["3 · Logistische Regression", "Lineares Modell mit ausgeglichenen Klassen; schnell und erklärbar."],
    ["4 · Score 0–1", "Wie ähnlich ist das Dokument einem Modulhandbuch?"],
  ];
  steps.forEach((st, i) => {
    const x = X0 + i * 3.08;
    box(s, x, 1.5, 2.85, 2.35, C.background2, "Modell " + (i + 1));
    T(s, st[0], { x: x + 0.2, y: 1.62, w: 2.45, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
    T(s, st[1], { x: x + 0.2, y: 2.1, w: 2.45, h: 1.7, fontSize: 14 });
    if (i < 3) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.87, y: 2.5, w: 0.2, h: 0.35, fill: { color: C.accent4 }, line: { color: C.accent4, width: 0 }, objectName: "Pfeil" });
  });
  T(s, "Dreiteilige Entscheidung statt Ja/Nein", { x: X0, y: 4.05, w: CW, h: 0.35, fontSize: 16, bold: true, color: C.text2 });
  const dec = [["Score ≤ untere Schwelle", "automatisch negativ – verworfen", C.background2, C.text1], ["dazwischen", "unsicher – Sprachmodell bzw. Review", C.accent5, C.text1], ["Score ≥ obere Schwelle", "automatisch positiv – übernommen", C.accent1, C.background1]];
  dec.forEach((d, i) => {
    const x = X0 + i * 4.1;
    box(s, x, 4.5, 3.93, 1.0, d[2], "Entscheidung " + (i + 1));
    T(s, [{ text: d[0], options: { bold: true, breakLine: true } }, { text: d[1], options: {} }], { x: x + 0.2, y: 4.5, w: 3.5, h: 1.0, fontSize: 14, color: d[3], valign: "middle" });
  });
  T(s, "Schwellen werden aus den Trainingsdaten abgeleitet (Recall-Ziel 95 %), nicht fest auf 0,5 gesetzt; für den Live-Crawl wird 0,8 empfohlen. Bewusst kein Transformer: schnell auf CPU (165.000 PDFs in Stunden), erklärbar, ehrlich evaluierbar.", { x: X0, y: 5.75, w: CW, h: 1.0, fontSize: 14, color: C.text1 });
}

// ---------------------------------------------------------------- ML-Modell: Training
{
  const s = content("Backup: Training und Evaluation des ML-Modells",
    "Datenbasis: Zu Beginn 202 gelabelte Dokumente von 21 Hochschulen (134 positiv, 68 negativ), später 2.695 Dokumente von 269 Hochschulen. Die Daten liegen in Ordnern positiv/negativ je Hochschule; exakte Duplikate werden per Text-Hash entfernt. Aufteilung: StratifiedGroupKFold mit 5 Folds, gruppiert nach Hochschule – keine Hochschule ist gleichzeitig in Training und Test. Das misst die schwere, realistische Frage: Erkennt das Modell Modulhandbücher von Hochschulen, die es nie gesehen hat? Schwellen: Die untere wird so gewählt, dass der Recall mindestens 95 % beträgt; die obere so, dass die Precision mindestens 95 % beträgt. Leakage-Check: Es werden zwei Varianten trainiert – nur Inhalt, und Inhalt plus Dateiname/Titel. Waren sie sehr unterschiedlich, würde das Modell vermutlich Dateinamen lesen; sie waren fast gleich (PR-AUC 0,957 vs. 0,960), daher gewinnt die schlankere Inhalts-Variante. Erste Baseline: Recall 95,5 %, Precision 87,1 % bei Ziel-Recall. Human-in-the-Loop: Verdikte aus der Review-Oberfläche werden ins Trainingsset übernommen und das Modell neu trainiert. Das Diagramm zeigt die wichtigste Lehre: In der Praxis ist die Bestätigungsrate bei niedrigen Scores sehr gering, erst ab Score 0,9 hoch.");
  box(s, X0, 1.5, 6.1, 5.3, C.background2, "Training Text");
  T(s, bullets([
    { text: "Daten: erst 202 Dokumente (21 Hochschulen), später 2.695 Dokumente (269 Hochschulen); Duplikate per Text-Hash entfernt", options: {} },
    "Split: 5-fach, gruppiert nach Hochschule – keine Hochschule in Training und Test (misst Generalisierung auf unbekannte Hochschulen)",
    "Schwellen aus den Daten: untere für 95 % Recall, obere für 95 % Precision",
    "Leakage-Check: Inhalt allein vs. Inhalt + Dateiname/Titel – fast gleich (PR-AUC 0,957 / 0,960), daher schlankes Modell",
    "Erste Baseline: Recall 95,5 %, Precision 87,1 % bei Ziel-Recall",
    "Human-in-the-Loop: Review-Verdikte fließen ins Trainingsset, Modell wird neu trainiert",
  ]), { x: X0 + 0.25, y: 1.65, w: 5.6, h: 5.0, fontSize: 14, paraSpaceAfter: 8 });
  T(s, "Praxis: Anteil vom Sprachmodell bestätigter Treffer je Score-Bereich", { x: 7.0, y: 1.5, w: 5.73, h: 0.55, fontSize: 15, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: "Bestätigt", labels: ["0,5–0,6", "0,6–0,7", "0,7–0,8", "0,8–0,9", "≥ 0,9"], values: [7.8, 12.7, 30.3, 44.3, 82.5] }],
    chartBase({ x: 7.0, y: 2.1, w: 5.73, h: 4.1, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 100, chartColors: [H.accent1], dataLabelFormatCode: '0.0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 40, dataLabelFontSize: 14, catAxisLabelFontSize: 13 }));
  T(s, "Je höher der Score, desto verlässlicher – aber erst ab 0,9 wirklich hoch.", { x: 7.0, y: 6.3, w: 5.73, h: 0.5, fontSize: 13, color: C.accent4 });
}

// ---------------------------------------------------------------- Sprachmodell-Stufe
{
  const s = content("Backup: Zweite Stufe – Prüfung durch das Sprachmodell",
    "Die zweite Stufe fragt ein Sprachmodell (Claude Haiku 4.5 über Amazon Bedrock): Passt dieses Dokument zur Definition? Der Prompt entsteht aus einer 'Spec': Definition plus Gegenbeispiele (Prüfungsordnung, einzelnes Modulblatt, Vorlesungsverzeichnis, Flyer, Antrag). Das Modell sieht die ersten 8.000 Zeichen und antwortet als kompaktes JSON: is_match, confidence und eine Begründung in höchstens 12 Wörtern. Ein Urteil zählt als bestätigt bei Konfidenz ab 0,8. Geprüft wurden 34.141 Dokumente mit je rund 2.300 Eingabe-Token, Kosten rund 107 $ (ca. 3,10 $ je 1.000 Dokumente). Würde man alle 164.396 Dokumente so prüfen, wären es hochgerechnet etwa 500 $ und deutlich mehr Laufzeit – deshalb die zweistufige Lösung. Grenzen: Das Modell sieht nur den Textanfang; zwei echte Handbücher wurden in der Stichprobe verworfen, weil sie mit einer Studienordnung beginnen. Übereinstimmung mit manueller Stichprobe: 85 % (17 von 20, kleine Stichprobe).");
  box(s, X0, 1.5, 6.4, 3.0, C.background2, "Spec");
  T(s, "Die Spec: Definition und Gegenbeispiele als Daten", { x: X0 + 0.25, y: 1.62, w: 5.9, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  T(s, [
    { text: "Match: ", options: { bold: true } }, { text: "systematisches Modulhandbuch eines Studiengangs – je Modul Lernergebnisse, Inhalte, ECTS/SWS, Prüfungsform.", options: { breakLine: true } },
    { text: "Kein Match: ", options: { bold: true } }, { text: "Prüfungs-/Studienordnung, einzelnes Modulblatt, Vorlesungsverzeichnis, Flyer, Antrag, allgemeine Studieninfo.", options: { breakLine: true } },
    { text: "Antwort: ", options: { bold: true } }, { text: '{"is_match": true|false, "confidence": 0–1, "reason": "≤ 12 Wörter"}', options: {} },
  ], { x: X0 + 0.25, y: 2.1, w: 5.9, h: 2.3, fontSize: 14, paraSpaceAfter: 8 });
  box(s, X0, 4.7, 6.4, 2.1, C.background2, "Grenzen");
  T(s, [
    { text: "Grenzen", options: { bold: true, color: C.text2, breakLine: true, fontSize: 16 } },
    { text: "Nur die ersten 8.000 Zeichen werden gesehen: Studienordnungen mit Modulbeschreibungen werden manchmal verworfen. Manuelle Stichprobe: 17 von 20 Urteilen stimmen überein (85 %, kleine Stichprobe).", options: {} },
  ], { x: X0 + 0.25, y: 4.8, w: 5.9, h: 1.95, fontSize: 14, paraSpaceAfter: 6 });
  const tiles = [["34.141", "Dokumente geprüft"], ["≈ 2.300", "Eingabe-Token je Dokument"], ["107 $", "≈ 3,10 $ je 1.000 Dokumente"], ["≈ 500 $", "wenn alle 164.396 Dokumente geprüft würden"]];
  tiles.forEach((t, i) => {
    const x = 7.3 + (i % 2) * 2.8, y = 1.5 + Math.floor(i / 2) * 2.7;
    box(s, x, y, 2.65, 2.5, C.background2, "Zahl " + (i + 1));
    T(s, t[0], { x: x + 0.15, y: y + 0.2, w: 2.35, h: 0.8, fontSize: 30, bold: true, color: C.accent1, valign: "middle" });
    T(s, t[1], { x: x + 0.15, y: y + 1.1, w: 2.35, h: 1.3, fontSize: 14 });
  });
  T(s, "Modell: Claude Haiku 4.5 (Amazon Bedrock). Urteil gilt bei Konfidenz ≥ 0,8.", { x: 7.3, y: 6.5, w: 5.4, h: 0.4, fontSize: 12, color: C.accent4 });
}

// ---------------------------------------------------------------- Modularität 1
{
  const s = content("Backup: Modularität – was austauschbar ist",
    "Die Plattform trennt konsequent das Generische vom Anwendungsfall. Generisch bleibt die Crawl-Engine (Scrapy: Tiefen- und Seitenbudget, robots.txt, Deduplizierung, Parallelität). Austauschbar sind: das Extraction Profile (was folgen, was herunterladen, was extrahieren – heute 'generic', 'modulhandbuch' und 'html-content'), die Suchbegriffe für die Discovery, das ML-Modell (eigene Trainingsdaten), die Spec für die Sprachmodell-Stufe (Prompt als Daten), die Pipelines für Ablage und Klassifikation sowie in der Webapp die Zuordnung von Modellen zu Rollen. Drei Extraktionsformen sind vorgesehen: Dokumente ernten (PDF/DOC), HTML-Inhalt je Seite (ContentItem) und strukturierte Felder (z. B. Datum, Ort per CSS/XPath). Ein neuer Dokumenttyp ist damit Konfiguration plus Daten, kein neuer Crawler.");
  const rows = [
    [hc("Baustein"), hc("Austauschbar"), hc("Heute")],
    [tc("Crawl-Engine", true), tc("nein – generisch: Tiefe, Seitenbudget, robots.txt, Dedup, Parallelität"), tc("gleiche Engine für alle Fälle")],
    [tc("Extraction Profile", true), tc("was folgen, laden und extrahieren (Dokumente, HTML-Inhalt, Felder)"), tc("generic · modulhandbuch · html-content")],
    [tc("Discovery", true), tc("Suchbegriffe und URL-Stämme je Profil"), tc("Common Crawl, Serper, Firecrawl")],
    [tc("ML-Modell (Stufe 1)", true), tc("eigenes Modell aus eigenen Trainingsdaten"), tc("TF-IDF + logistische Regression")],
    [tc("Sprachmodell-Spec (Stufe 2)", true), tc("Prompt als Daten: Definition + Gegenbeispiele"), tc("Spec „modulhandbuch“")],
    [tc("Pipelines", true), tc("Ablage (S3/lokal) und Klassifikation als Pipeline-Schritte"), tc("Manifest mit Score und Begründung")],
    [tc("Webapp", true), tc("Modelle verwalten, Rollen zuordnen"), tc("Rolle „Modulhandbuch“")],
  ];
  s.addTable(rows, { x: X0, y: 1.5, w: CW, colW: [2.9, 5.6, 3.63], rowH: [0.45, 0.65, 0.65, 0.6, 0.6, 0.6, 0.65, 0.6], border: TB, margin: [0.04, 0.12, 0.04, 0.12], objectName: "Tabelle Modularität" });
  T(s, "Ein neuer Dokumenttyp ist Konfiguration plus Daten – kein neuer Crawler.", { x: X0, y: 6.45, w: CW, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
}

// ---------------------------------------------------------------- Modularität 2
{
  const s = content("Backup: Neuer Anwendungsfall in vier Schritten (Beispiel: KI-Richtlinien)",
    "Entwurf am Beispiel der eingereichten Bachelorarbeit – die konkreten Begriffe und Definitionen hängen vom Ausgang des Vorschlags ab. Schritt 1: Ein Profil als Unterklasse anlegen und in der Registry eintragen; es legt Schlüsselwörter mit Gewichten (zur Steuerung des Crawls), Suchbegriffe für die Discovery und die Zieldateien fest. Schritt 2: Eine Spec registrieren, also Definition und Gegenbeispiele – der Prompt entsteht daraus automatisch. Schritt 3: Kaltstart ohne Trainingsdaten – zuerst labelt das Sprachmodell, die Review-Oberfläche (Human-in-the-Loop) korrigiert, danach lässt sich ein schnelles ML-Modell wie bei den Modulhandbüchern trainieren. Schritt 4: Modell und Rolle in der Webapp zuordnen, Hochschulliste hochladen, Lauf starten. Wiederverwendet werden Crawler-Engine, Cloud-Betrieb, Hochschulliste, Review-Oberfläche, Evaluationsmodul und Kostenkontrolle.");
  const st = [
    ["1 · Profil anlegen", "Unterklasse von ExtractionProfile: Schlüsselwörter mit Gewichten (z. B. „ki“, „richtlinie“, „generative“), Discovery-Suchbegriffe, Zieldateien (PDF und HTML-Seiten); in der Registry eintragen."],
    ["2 · Spec definieren", "Definition: Hochschuldokument mit Regeln zum Umgang mit KI in Studium, Lehre oder Prüfungen. Gegenbeispiele: Pressemeldung, Projektbeschreibung, Veranstaltungshinweis."],
    ["3 · Kaltstart", "Ohne Trainingsdaten labelt zuerst das Sprachmodell; Review-Oberfläche korrigiert (Human-in-the-Loop); später ein schnelles ML-Modell trainieren."],
    ["4 · Bereitstellen", "Modell und Rolle in der Webapp zuordnen, Hochschulliste hochladen, Lauf starten. Auswertung und Kostenkontrolle laufen unverändert."],
  ];
  st.forEach((x, i) => {
    const px = X0 + i * 3.08;
    box(s, px, 1.5, 2.9, 4.0, C.background2, "Schritt " + (i + 1));
    T(s, x[0], { x: px + 0.2, y: 1.65, w: 2.5, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
    T(s, x[1], { x: px + 0.2, y: 2.2, w: 2.5, h: 3.2, fontSize: 14 });
  });
  T(s, "Wiederverwendet: Crawler-Engine, Cloud-Betrieb, Hochschulliste (404), Review-Oberfläche, Evaluationsmodul, Kostenkontrolle.", { x: X0, y: 5.75, w: CW, h: 0.5, fontSize: 16, bold: true, color: C.text2 });
  T(s, "Entwurf am Beispiel der Bachelorarbeit; Details abhängig vom Ausgang des Vorschlags.", { x: X0, y: 6.4, w: CW, h: 0.35, fontSize: 12, color: C.accent4 });
}

// ---------------------------------------------------------------- Discovery & Recall
{
  const s = content("Backup: Maßnahmen gegen Lücken (Discovery und Recall)",
    "Der erste Großlauf fand bei 145 Hochschulen keine Handbücher. Gegenmaßnahmen: Best-First-Crawl (Links mit Schlüsselwörtern wie 'Modulhandbuch' zuerst, damit das kleine Seitenbudget gut genutzt wird); Sitemaps; Fakultäts-Subdomains bekommen ein frisches Tiefenbudget (z. B. cs.tu-dortmund.de). Für Hochschulen ohne Treffer die Discovery: Common Crawl (kostenlos, öffentlicher Webindex; in Tests wurden etwa 60 % der gescheiterten Domains geborgen), Serper (Google-Suche; erreicht tief liegende Dateien; bei drei Test-Hochschulen mit null Treffern wurden gezielt 13 Handbücher gefunden) und Firecrawl (JavaScript-Rendering; gebaut, bisher ohne Großeinsatz). OCR für gescannte PDFs brachte bei hohem Aufwand nur 42 zusätzliche Treffer. Der Seeds-only-Modus erlaubt eine gezielte Nachsuche mit den gefundenen URLs.");
  const rows = [
    [hc("Maßnahme"), hc("Problem"), hc("Wirkung")],
    [tc("Best-First-Crawl", true), tc("kleines Seitenbudget"), tc("Handbuch-Seiten werden zuerst geholt")],
    [tc("Sitemaps, Fakultäts-Subdomains", true), tc("tief liegende Seiten, getrennte Server"), tc("zusätzliche Einstiege, frisches Tiefenbudget")],
    [tc("Common Crawl (kostenlos)", true), tc("Hochschulen mit 0 Treffern"), tc("in Tests ≈ 60 % der gescheiterten Domains geborgen")],
    [tc("Serper (Google-Suche)", true), tc("tief liegende, unverlinkte Dateien"), tc("13 Handbücher bei 3 Test-Hochschulen mit 0 Treffern")],
    [tc("Firecrawl (JS-Rendering)", true), tc("JavaScript-Portale"), tc("gebaut, noch kein Großeinsatz")],
    [tc("OCR (Tesseract)", true), tc("gescannte PDFs ohne Text"), tc("3.553 Scans, nur 42 zusätzliche Treffer")],
    [tc("Seeds-only-Modus", true), tc("gezielte Nachsuche"), tc("Nachlauf mit gefundenen URLs (+43 Hochschulen)")],
  ];
  s.addTable(rows, { x: X0, y: 1.5, w: CW, colW: [3.5, 3.8, 4.83], rowH: [0.45, 0.6, 0.65, 0.6, 0.65, 0.6, 0.6, 0.6], border: TB, margin: [0.04, 0.12, 0.04, 0.12], objectName: "Tabelle Recall" });
  T(s, "Ausgangslage: 145 Hochschulen ohne Treffer im ersten Großlauf; heute noch 39 ohne jeden Fund.", { x: X0, y: 6.4, w: CW, h: 0.4, fontSize: 14, color: C.accent4 });
}

// ---------------------------------------------------------------- Crawl-Regeln & Recht
{
  const s = content("Backup: Crawl-Regeln, Datenschutz und rechtliche Einordnung",
    "Keine Rechtsberatung – hier sind die offenen Punkte, die vor einer Veröffentlichung des Datensatzes zu klären sind. Technisch höflich: robots.txt wird standardmäßig befolgt; 1 Sekunde Verzögerung (zufällig variiert) mit AutoThrottle bis 10 Sekunden; maximal 2 parallele Anfragen je Domain; der Crawler bleibt auf der Domain der Hochschule; Dateien über 50 MB werden übersprungen; bereits besuchte URLs werden nicht erneut geholt. Offene Punkte: Es werden nur öffentlich zugängliche Dokumente erhoben, keine Logins. Im Seeds-only-Modus (opt-in, standardmäßig aus) umgehen gezielt per Suchmaschine gefundene Dokument-URLs die robots.txt – das ist vor einer Veröffentlichung zu bewerten. Urheber- und Nutzungsrechte: Für Forschung ist Text-und-Data-Mining nach § 60d UrhG relevant; die Weitergabe des Datensatzes ist zu klären. Modulhandbücher können Namen von Lehrenden enthalten – Datenschutz bei Weitergabe prüfen. Der User-Agent enthält noch eine Platzhalter-URL (github.com/yourorg) und sollte vor einem Echtbetrieb eine echte Kontaktadresse enthalten.");
  box(s, X0, 1.5, 5.95, 5.3, C.background2, "Höflichkeit");
  T(s, "Technische Höflichkeit", { x: X0 + 0.25, y: 1.65, w: 5.4, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  T(s, bullets([
    "robots.txt wird standardmäßig befolgt",
    "1 s Verzögerung (zufällig) plus AutoThrottle bis 10 s",
    "höchstens 2 parallele Anfragen je Domain",
    "bleibt auf der Domain der Hochschule",
    "Dateien über 50 MB werden übersprungen",
    "bereits besuchte URLs werden nicht erneut geholt",
  ]), { x: X0 + 0.25, y: 2.2, w: 5.4, h: 4.4, fontSize: 15, paraSpaceAfter: 10 });
  box(s, 6.78, 1.5, 5.95, 5.3, C.background2, "Offene Punkte");
  T(s, "Offene Punkte (zu klären)", { x: 7.03, y: 1.65, w: 5.4, h: 0.4, fontSize: 18, bold: true, color: C.accent2 });
  T(s, bullets([
    "Seeds-only-Modus (opt-in) umgeht robots.txt für gezielt gefundene Dokument-URLs – vor Veröffentlichung bewerten",
    "Urheberrecht: Text-und-Data-Mining für Forschung (§ 60d UrhG); Weitergabe des Datensatzes klären",
    "Datenschutz: Modulhandbücher können Namen von Lehrenden enthalten",
    "User-Agent: Platzhalter-URL durch echte Kontaktadresse ersetzen",
  ]), { x: 7.03, y: 2.2, w: 5.4, h: 4.4, fontSize: 15, paraSpaceAfter: 10 });
}

// ---------------------------------------------------------------- Betrieb & Sicherheit
{
  const s = content("Backup: Betrieb, Sicherheit und Zugriff",
    "Zugriff: Anmeldung mit bcrypt-gehashten Passwörtern, signierte Session-Tokens mit 12 Stunden Gültigkeit, eine Rollen-Matrix (Nutzer zu Rolle, KI-Modell zu Rolle), der Modell-Tab ist nur für Admins. Cloud: Jeder Dienst hat eine eigene IAM-Rolle mit begrenzten Rechten; das Deployment per GitHub Actions läuft über OIDC, also ohne langlebige Schlüssel. Ehrlich: Geheimnisse liegen derzeit in einer .env-Datei (geplant: Secrets Manager), das HTTPS-Zertifikat ist selbstsigniert (geplant: echtes Zertifikat). Betrieb: Push auf main startet CI/CD (Image bauen, Lambda aktualisieren, Webapp per SSM aktualisieren). Die Cloud-Umgebung ist befristet und wird nach Ablauf komplett gelöscht – deshalb lässt sie sich per Skript in einem Lauf neu aufbauen. Die Webapp (EC2 t3.small, ca. 0,58 $/Tag) läuft dauerhaft und kostete mehr als alle Crawls; ein Betrieb nur bei Bedarf wäre günstiger. Weitere Ausbaustufen: SQLite zu RDS bei mehreren Schreibern, Auto-Scaling hinter einem Load Balancer, automatisierte Tests und Monitoring.");
  const cols = [
    ["Zugriff", ["Login mit bcrypt-Hashes", "Session-Token, 12 h gültig", "Rollen-Matrix: Nutzer ↔ Rolle, KI-Modell ↔ Rolle", "Modell-Verwaltung nur für Admins"]],
    ["Cloud", ["eigene IAM-Rolle je Dienst", "Deployment per GitHub OIDC statt Schlüssel", "Geheimnisse noch in .env → Secrets Manager geplant", "HTTPS selbstsigniert → echtes Zertifikat geplant"]],
    ["Betrieb", ["CI/CD: Push auf main aktualisiert alles", "Neuaufbau der Umgebung per Skript", "Webapp ≈ 0,58 $/Tag – nur bei Bedarf wäre günstiger", "Ausbau: RDS, Auto-Scaling, Tests, Monitoring"]],
  ];
  cols.forEach((c, i) => {
    const x = X0 + i * 4.115;
    box(s, x, 1.5, 3.9, 0.55, C.accent1, "Kopf " + c[0]);
    T(s, c[0], { x: x + 0.25, y: 1.5, w: 3.4, h: 0.55, fontSize: 18, bold: true, color: C.background1, valign: "middle" });
    box(s, x, 2.05, 3.9, 4.75, C.background2, "Liste " + c[0]);
    T(s, bullets(c[1]), { x: x + 0.25, y: 2.25, w: 3.4, h: 4.4, fontSize: 15, paraSpaceAfter: 12 });
  });
}

// ---------------------------------------------------------------- Evaluationsmethodik
{
  const s = content("Backup: Wie die Qualitätszahlen entstanden sind",
    "Wichtig für Rückfragen zur Belastbarkeit. Alle Precision-Angaben messen die Übereinstimmung mit dem Urteil des Sprachmodells, nicht mit einem Menschen. Training: 5-fache Kreuzvalidierung gruppiert nach Hochschule (96,5 %). Praxis: Für Scores von 0,5 bis 0,9 hat das Sprachmodell rund 21.000 Dokumente geprüft, 25 % bestätigt. Pilot: Eine Stichprobe von 400 Dokumenten mit Score ab 0,9 ergab 82,5 % (95-%-Intervall 78,5–85,9 %). Auf 'nicht verdächtigen' Hosts bestätigte das Sprachmodell 212 von 225 (94,2 %), auf 197 'verdächtigen' Hosts (dort bestätigt das Sprachmodell sonst unter 30 %) nur 68 % von 6.463 vollständig geprüften Dokumenten. Das gezielte Nachprüfen dieser Hosts hob die geschätzte Precision der Endliste von ca. 89 % auf ca. 98 %. Manuelle Gegenprobe: 17 von 20 Urteilen stimmen überein (85 %, breites Intervall). Recall: grob geschätzt etwa 383 verpasste Handbücher bei 18.252 ungeprüften Dokumenten mit Score 0,3–0,5 – sehr unsicher. Der Zielwert von 40.000 ist eine Fachschätzung, keine Messung. Es gibt zwei Endlisten: streng (nur vom Sprachmodell bestätigt, 11.771) und erweitert (zusätzlich Score ≥ 0,9, 19.049).");
  const rows = [
    [hc("Messung"), hc("Methode"), hc("Ergebnis")],
    [tc("Training", true), tc("5-fach, gruppiert nach Hochschule"), tc("Precision 96,5 %")],
    [tc("Praxis, Score 0,5–0,9", true), tc("Sprachmodell prüft ≈ 21.000 Dokumente"), tc("25 % bestätigt")],
    [tc("Pilot, Score ≥ 0,9", true), tc("Stichprobe 400 Dokumente"), tc("82,5 % (Intervall 78,5–85,9)")],
    [tc("Unauffällige Hosts", true), tc("Stichprobe 225 Dokumente"), tc("94,2 % (Intervall 90,4–96,6)")],
    [tc("Verdächtige Hosts (197)", true), tc("alle 6.463 Dokumente geprüft"), tc("68 % bestätigt")],
    [tc("Endliste (erweitert)", true), tc("Hochrechnung aus den Zeilen oben"), tc("≈ 18.600 echt von 19.049 (≈ 98 %)")],
    [tc("Sprachmodell vs. Mensch", true), tc("20 Dokumente manuell geprüft"), tc("85 % Übereinstimmung (kleine Stichprobe)")],
    [tc("Recall", true), tc("grobe Stichprobe bei Score 0,3–0,5"), tc("≈ 383 verpasst bei 18.252 – sehr unsicher")],
    [tc("Zielwert 40.000", true), tc("Fachschätzung"), tc("Größenordnung, keine Messung")],
  ];
  s.addTable(rows, { x: X0, y: 1.45, w: CW, colW: [3.2, 4.4, 4.53], rowH: 0.5, border: TB, margin: [0.03, 0.12, 0.03, 0.12], objectName: "Tabelle Evaluation" });
  T(s, "Alle Precision-Angaben messen die Übereinstimmung mit dem Sprachmodell, nicht mit Menschen. Endlisten: streng (11.771, nur LLM-bestätigt) und erweitert (19.049).", { x: X0, y: 6.55, w: CW, h: 0.4, fontSize: 13, bold: true, color: C.text2 });
}

// ---------------------------------------------------------------- FAQ
{
  const s = content("Backup: Häufige Fragen",
    "Antworten auf erwartbare Rückfragen. Warum nicht alles mit dem Sprachmodell? Kosten und Zeit: hochgerechnet etwa 500 $ statt 107 $. Warum kein Transformer? Der Engpass war die Breite der Trainingsdaten, nicht die Modellgröße; TF-IDF ist schnell, erklärbar und ehrlich evaluierbar. Warum nicht nach Dateinamen filtern? Der Dateiname ist ein starkes Signal (bei Score ≥ 0,9: 95 % Bestätigung mit Stichwort 'modul/handbuch/mhb' gegenüber 35 % ohne), aber nicht allein ausreichend, weil Prüfungsordnungen ähnlich heißen. Aktualität: Stand August bis September 2026; ein kompletter Lauf dauert ca. 13 Stunden und ist wiederholbar. Nutzung der Daten: Weitergabe rechtlich zu klären. Aufwand für einen neuen Anwendungsfall: Profil und Spec sind Konfiguration; Hauptkosten ist die Prüfung mit ca. 3 $ je 1.000 Dokumente.");
  const qa = [
    ["Warum nicht alles mit dem Sprachmodell prüfen?", "Hochgerechnet ≈ 500 $ statt 107 $ und deutlich länger. Zweistufig ist es billiger und schneller."],
    ["Warum kein Transformer?", "Der Engpass war die Breite der Trainingsdaten, nicht die Modellgröße. TF-IDF ist schnell, erklärbar und ehrlich evaluierbar."],
    ["Warum nicht nach Dateinamen filtern?", "Starkes Signal (95 % vs. 35 % bei Score ≥ 0,9), aber nicht allein ausreichend: Prüfungsordnungen heißen ähnlich."],
    ["Wie aktuell sind die Daten?", "Stand August bis September 2026. Ein kompletter Lauf dauert ≈ 13 Stunden und ist wiederholbar."],
    ["Wer darf die Daten nutzen?", "Projektintern ja; Weitergabe ist rechtlich zu klären (Urheberrecht, Datenschutz)."],
    ["Was kostet ein neuer Anwendungsfall?", "Profil und Spec sind Konfiguration. Hauptkosten: Prüfung, ≈ 3 $ je 1.000 Dokumente."],
  ];
  qa.forEach((q, i) => {
    const x = X0 + (i % 2) * 6.15, y = 1.5 + Math.floor(i / 2) * 1.8;
    box(s, x, y, 5.98, 1.65, C.background2, "FAQ " + (i + 1));
    T(s, q[0], { x: x + 0.2, y: y + 0.1, w: 5.6, h: 0.4, fontSize: 15, bold: true, color: C.accent1 });
    T(s, q[1], { x: x + 0.2, y: y + 0.55, w: 5.6, h: 1.05, fontSize: 14 });
  });
}

// ================================================================ B3 Fehlerarten
{
  const s = content("Backup: Typische Fehler des ML-Modells",
    "Von 20.031 TF-IDF-Positiven, die das Sprachmodell verworfen hat. Die Zuordnung erfolgt per Stichwort aus der Begründung des Sprachmodells und ist daher grob. Die Hälfte sind Prüfungs- oder Studienordnungen, 21 % Einzelmodulblätter. Daraus folgt: Der Klassifikator erkennt 'Dokument über Studium', nicht 'Dokument im Format Modulhandbuch'.");
  T(s, "Falsche Treffer nach Dokumentart (Anzahl, insgesamt 20.031)", { x: X0, y: 1.5, w: CW, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{
    name: "Dokumente",
    labels: ["Prüfungs-/Studienordnung, Satzung", "Einzelnes Modul / Datenblatt", "Studienverlaufs-/Studienplan", "Sonstiges", "Modul-/Wahlpflichtkatalog (unvollständig)", "Vorlesungsverzeichnis", "Antrag, Formular, Flyer"],
    values: [9919, 4107, 2080, 1827, 933, 737, 428],
  }], chartBase({ x: X0, y: 1.95, w: CW, h: 4.6, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, chartColors: [H.accent2], dataLabelFormatCode: "#,##0", dataLabelPosition: "outEnd", barGapWidthPct: 35, catAxisLabelFontSize: 14, dataLabelFontSize: 14, valAxisMaxVal: 11500 }));
}

// ================================================================ B4 Kosten pro Tag
{
  const s = content("Backup: Cloud-Kosten pro Tag",
    "Tägliche Kosten ab dem 12.08.2026 (Gesamt 152,22 $ in diesem Zeitraum). Spitzen entsprechen den Großläufen (12.08., 16.09.) und den Tagen der Sprachmodell-Prüfung (02.09., 30.09., 01.10., 02.10.). Die Grundlast von ca. 0,27–0,77 $ pro Tag ist die dauerhaft laufende Webapp (Server, feste IP-Adresse, Datenträger).");
  T(s, "Kosten pro Tag in US-Dollar (12.08. bis 05.10.2026)", { x: X0, y: 1.5, w: CW, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
  const labels = days.map((d, i) => (i % 7 === 0 ? d[0].slice(8, 10) + "." + d[0].slice(5, 7) + "." : " ".repeat((i % 7) + 1)));
  s.addChart(pres.charts.BAR, [{ name: "Kosten", labels, values: days.map((d) => Math.round(d[1] * 100) / 100) }],
    chartBase({ x: X0, y: 1.95, w: CW, h: 4.3, barDir: "col", showValue: false, chartColors: [H.accent1], barGapWidthPct: 20, valAxisLabelFormatCode: '0" $"', catAxisLabelFontSize: 11 }));
  T(s, "Spitzen: Großläufe (12.08., 16.09.) und Sprachmodell-Prüfung (02.09., 30.09. – 02.10.). Grundlast: laufende Webapp.", { x: X0, y: 6.35, w: CW, h: 0.4, fontSize: 13, color: C.accent4 });
}

// ================================================================ B5 Abdeckung Typ & Bundesland
{
  const s = content("Backup: Abdeckung nach Hochschultyp und Bundesland",
    "Anteil der Hochschulen mit mindestens einem Modulhandbuch in der erweiterten Endliste. In Klammern die Anzahl der Hochschulen. Kleine Bundesländer mit wenigen Hochschulen (Saarland, Bremen) sind statistisch wenig belastbar.");
  T(s, "Nach Hochschultyp (Anzahl Hochschulen)", { x: X0, y: 1.5, w: 4.3, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: "Abdeckung", labels: ["Universität (120)", "Künstlerisch (56)", "FH / HAW (194)", "Verwaltung (27)"], values: [76, 70, 60, 44] }],
    chartBase({ x: X0, y: 1.95, w: 4.3, h: 4.5, barDir: "col", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 100, chartColors: [H.accent1], dataLabelFormatCode: '0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 50, catAxisLabelFontSize: 11, dataLabelFontSize: 13 }));
  T(s, "Nach Bundesland (Anzahl Hochschulen)", { x: 5.3, y: 1.5, w: 7.43, h: 0.4, fontSize: 15, bold: true, color: C.text2 });
  const land = [["Bremen (7)", 86], ["Hamburg (17)", 82], ["Sachsen (20)", 75], ["Bayern (43)", 74], ["Nordrhein-Westf. (62)", 73], ["Niedersachsen (30)", 73], ["Mecklenburg-Vorp. (7)", 71], ["Sachsen-Anhalt (10)", 70], ["Baden-Württemberg (68)", 65], ["Rheinland-Pfalz (20)", 65], ["Schleswig-Holstein (13)", 62], ["Thüringen (13)", 62], ["Brandenburg (20)", 50], ["Berlin (34)", 47], ["Hessen (33)", 45], ["Saarland (6)", 33]];
  s.addChart(pres.charts.BAR, [{ name: "Abdeckung", labels: land.map((l) => l[0]), values: land.map((l) => l[1]) }],
    chartBase({ x: 5.3, y: 1.95, w: 7.43, h: 4.9, barDir: "bar", catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 100, chartColors: [H.accent1], dataLabelFormatCode: '0" %"', dataLabelPosition: "outEnd", barGapWidthPct: 25, catAxisLabelFontSize: 11, dataLabelFontSize: 11 }));
}

// ================================================================ B6 Projektverlauf
{
  const s = content("Backup: Projektverlauf in vier Phasen",
    "Kurzüberblick über den Weg von Juni bis Oktober 2026. Phase 1: Prototyp und Cloud-Grundgerüst. Phase 2: MVP, erster Klassifikator, Review-Oberfläche, Automatisierung. Phase 3: Erster Großlauf über 411 Hochschulen, Analyse der Lücken, Zusatzsuche, Sprachmodell-Stufe. Phase 4: Deep Run, großflächige Prüfung, Abschlussauswertung.");
  const ph = [
    ["Phase 1 · Juni–Juli", "Prototyp & Cloud", ["Scrapy-Prototyp", "AWS: Lambda, S3, DynamoDB", "Login, Rollen, Webapp auf EC2"]],
    ["Phase 2 · Juli", "MVP", ["Erster Klassifikator", "Review-Oberfläche und Nachtraining", "CI/CD, fokussierter Crawl"]],
    ["Phase 3 · August–September", "Großlauf & Qualität", ["Lauf über 411 Hochschulen (6,3 h)", "Zusatzsuche, OCR", "Sprachmodell-Zweitstufe"]],
    ["Phase 4 · September–Oktober", "Deep Run & Auswertung", ["Deep Run: 132.187 PDFs in 13 h", "Prüfung von ≈ 34.000 Dokumenten", "Abschlussauswertung, Projektbericht"]],
  ];
  ph.forEach((p, i) => {
    const x = X0 + i * 3.08;
    box(s, x, 1.65, 2.9, 4.4, C.background2, "Phase " + (i + 1));
    T(s, p[0], { x: x + 0.2, y: 1.85, w: 2.5, h: 0.5, fontSize: 13, bold: true, color: C.accent1 });
    T(s, p[1], { x: x + 0.2, y: 2.4, w: 2.5, h: 0.8, fontSize: 19, bold: true, color: C.text2 });
    T(s, bullets(p[2]), { x: x + 0.2, y: 3.35, w: 2.5, h: 2.5, fontSize: 14, paraSpaceAfter: 8 });
  });
}


// ================================================================ Glossar
function glossary(title, items, notes) {
  const s = content(title, notes);
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 14, valign: "middle" } });
  const rows = [[hdr("Begriff"), hdr("Bedeutung")]].concat(items.map((i) => [
    { text: i[0], options: { bold: true, fontSize: 14, valign: "middle" } },
    { text: i[1], options: { fontSize: 14, valign: "middle" } },
  ]));
  s.addTable(rows, { x: X0, y: 1.5, w: CW, colW: [2.9, 9.23], rowH: 0.55, border: { type: "solid", pt: 0.75, color: "D5DBE3" }, margin: [0.04, 0.12, 0.04, 0.12], objectName: "Tabelle Glossar" });
}
glossary("Backup: Glossar (1/2) – Cloud und Betrieb", [
  ["AWS", "Amazon Web Services: Cloud-Plattform, auf der Rechenleistung, Speicher und Dienste gemietet werden"],
  ["Fargate / Lambda", "AWS-Dienste, die Programme nur für die Dauer der Aufgabe ausführen und abrechnen"],
  ["S3 / DynamoDB", "AWS-Dienste für Dateispeicher bzw. eine schnelle Merkliste (Datenbank)"],
  ["Bedrock", "AWS-Dienst, über den Sprachmodelle wie Claude als Cloud-Dienst genutzt werden"],
  ["Deployment / CI/CD", "Bereitstellen einer Software auf einem Server; CI/CD macht das bei jedem Push automatisch"],
  ["Asynchron", "Aufgaben laufen im Hintergrund; man muss nicht vor dem Bildschirm warten"],
  ["Vollerhebung", "Alle Modulhandbücher aller deutschen Hochschulen erfassen (Fachschätzung ca. 40.000)"],
], "Für Rückfragen. Begriffe bei Bedarf schon im Vortrag beim ersten Auftreten in einem Satz erklären.");
glossary("Backup: Glossar (2/2) – Daten und Machine Learning", [
  ["Crawler / Spider", "Programm, das Webseiten automatisch durchläuft, Links folgt und Dateien sammelt (Spider = Crawler im Framework Scrapy)"],
  ["Manifest", "Protokolldatei mit einer Zeile je Dokument: Herkunft, Score, Entscheidung, Begründung"],
  ["TF-IDF", "Verfahren, das Texte anhand der Wichtigkeit ihrer Wörter in Zahlen überführt"],
  ["Klassifikator", "Modell, das ein Dokument einer Klasse zuordnet (hier: Modulhandbuch ja/nein)"],
  ["Sprachmodell (LLM)", "KI-Modell, das Texte versteht und erzeugt (hier: Claude Haiku 4.5)"],
  ["Human-in-the-Loop", "Ein Mensch prüft die unsicheren Fälle; sein Urteil fließt ins Nachtraining ein"],
  ["OCR", "Texterkennung für gescannte Dokumente"],
  ["Precision / Recall", "Precision: Anteil richtiger Treffer unter den gefundenen. Recall: Anteil der gefundenen unter allen vorhandenen"],
], "Für Rückfragen.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})();
