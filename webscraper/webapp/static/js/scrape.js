// Section "Scraping" (Abschnitt 1).
import { api, apiForm, getToken } from "./api.js";

// The two human verdicts (model-agnostic on purpose — see scrape.py). For this
// model, positive = Modulhandbuch. Only the button captions are MH-specific.
const VERDICT_LABELS = { positive: "Modulhandbuch", negative: "Kein MH" };

// Client-side review selection for the current run: { [manifestIndex]: verdict }.
// Populated by clicks, flushed to the server in one batch by "Prüfung abschließen".
let selectedVerdicts = {};

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadFileTypes() {
  const data = await api("/api/scrape/filetypes");
  const wrap = document.getElementById("sc-filetypes");
  wrap.innerHTML = "";
  for (const [group, items] of Object.entries(data.groups)) {
    const fs = document.createElement("fieldset");
    fs.className = "ft-group";
    let html = `<legend>${escapeHtml(group)}</legend><div class="ft-grid">`;
    for (const it of items) {
      html +=
        `<label class="ft-item"><input type="checkbox" class="ft-cb" ` +
        `value="${it.ext}" /> ${escapeHtml(it.label)}</label>`;
    }
    html += "</div>";
    fs.innerHTML = html;
    wrap.appendChild(fs);
  }
  wrap.querySelectorAll(".ft-cb").forEach((cb) =>
    cb.addEventListener("change", updateButtonState)
  );
}

async function loadModels() {
  const data = await api("/api/scrape/models");
  const select = document.getElementById("sc-model");
  const empty = document.getElementById("sc-model-empty");
  select.innerHTML = "";
  if (data.models.length === 0) {
    empty.style.display = "block";
    select.style.display = "none";
  } else {
    empty.style.display = "none";
    select.style.display = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "Bitte wählen…";
    select.appendChild(ph);
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.bezeichnung;
      select.appendChild(opt);
    }
  }
}

function selectedFileTypes() {
  return Array.from(document.querySelectorAll(".ft-cb:checked")).map((cb) => cb.value);
}

function hasSource() {
  const url = document.getElementById("sc-url").value.trim();
  const file = document.getElementById("sc-file").files.length > 0;
  return Boolean(url) || file;
}

function updateButtonState() {
  const btn = document.getElementById("sc-start");
  const hint = document.getElementById("sc-hint");
  const model = document.getElementById("sc-model").value;

  const reasons = [];
  if (selectedFileTypes().length === 0) reasons.push("mind. 1 Dateiformat");
  // KI-Modell ist vorerst optional (bis ein Modell trainiert wurde).
  if (!hasSource()) reasons.push("URL oder Datei");
  void model;

  btn.disabled = reasons.length > 0;
  hint.textContent = reasons.length ? "Fehlt: " + reasons.join(", ") : "";
}

async function loadLog() {
  const data = await api("/api/scrape/log");
  const log = document.getElementById("sc-log");
  log.textContent = data.lines.length
    ? data.lines.join("\n")
    : "Noch kein Lauf gestartet.";
  log.scrollTop = log.scrollHeight; // show the latest lines
}

// ---------------------------------------------------------------------------
// Progress + results dashboard
// ---------------------------------------------------------------------------

const STATUS_LABELS = {
  scraped: "Erfolgreich",
  skipped: "Übersprungen",
  invalid: "Ungültig",
  error: "Fehler",
  pending: "Ausstehend",
};

function fmtBytes(n) {
  const mb = (n || 0) / (1024 * 1024);
  if (mb >= 1) return mb.toFixed(2) + " MB";
  return ((n || 0) / 1024).toFixed(1) + " KB";
}

function showResultCard() {
  document.getElementById("sc-result-card").style.display = "";
}

function renderProgress(job) {
  const el = document.getElementById("sc-progress");
  const results = document.getElementById("sc-results");
  if (job.status === "running") {
    results.innerHTML = "";
    el.innerHTML =
      `<div class="progress-wrap"><div class="progress-bar indeterminate"></div></div>` +
      `<p class="muted">Scraping läuft … <strong>${job.elapsed_seconds}s</strong>` +
      ` · ${job.urls.length} URL(s) · ${escapeHtml(job.file_types.join(", "))}</p>`;
  } else {
    el.innerHTML = "";
  }
}

function tile(label, value) {
  return (
    `<div class="stat-tile"><div class="stat-value">${escapeHtml(String(value))}</div>` +
    `<div class="stat-label">${escapeHtml(label)}</div></div>`
  );
}

function bar(label, value, max, cls) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    `<div class="cmp-row"><span class="cmp-label">${escapeHtml(label)}</span>` +
    `<span class="cmp-track"><span class="cmp-fill ${cls}" style="width:${pct}%"></span></span>` +
    `<span class="cmp-num">${value}</span></div>`
  );
}

function renderResults(job) {
  const results = document.getElementById("sc-results");
  const s = job.summary;

  if (!s) {
    const cls = job.status === "error" ? "err" : "muted";
    results.innerHTML =
      `<p class="${cls}">${escapeHtml(job.detail || "Keine Ergebnisdaten verfügbar.")}</p>`;
    return;
  }

  // Summary tiles ----------------------------------------------------------
  let html =
    `<div class="stat-grid">` +
    tile("URLs", s.total_urls) +
    tile("Gefunden", s.files_found) +
    tile("Heruntergeladen", s.files_downloaded) +
    tile("Datenmenge", fmtBytes(s.bytes_downloaded)) +
    tile("Dauer", (s.duration_seconds || 0) + " s") +
    `</div>`;

  // Found vs downloaded graphic -------------------------------------------
  const max = Math.max(s.files_found, s.files_downloaded, 1);
  html +=
    `<div class="cmp-chart">` +
    bar("Gefunden", s.files_found, max, "fill-found") +
    bar("Heruntergeladen", s.files_downloaded, max, "fill-dl") +
    `</div>`;

  // Status badges ----------------------------------------------------------
  const counts = s.counts || {};
  const badges = Object.keys(counts)
    .map(
      (k) =>
        `<span class="badge badge-${k}">${escapeHtml(STATUS_LABELS[k] || k)}: ${counts[k]}</span>`
    )
    .join(" ");
  if (badges) html += `<div class="badge-row">${badges}</div>`;

  // Per-URL table ----------------------------------------------------------
  const rows = (s.per_url || [])
    .map((r) => {
      const detail = r.detail ? escapeHtml(r.detail) : "";
      return (
        `<tr><td class="url-cell" title="${escapeHtml(r.url)}">${escapeHtml(r.url)}</td>` +
        `<td><span class="badge badge-${r.status}">${escapeHtml(
          STATUS_LABELS[r.status] || r.status
        )}</span></td>` +
        `<td class="num">${r.files_found}</td>` +
        `<td class="num">${r.files_downloaded}</td>` +
        `<td class="num">${fmtBytes(r.bytes_downloaded)}</td>` +
        `<td class="muted small">${detail}</td></tr>`
      );
    })
    .join("");
  if (rows) {
    html +=
      `<div class="table-scroll"><table class="result-table">` +
      `<thead><tr><th>URL</th><th>Status</th><th>Gefunden</th>` +
      `<th>Geladen</th><th>Größe</th><th>Detail</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`;
  }

  results.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Classification results — the "relevant Modulhandbücher" view
// ---------------------------------------------------------------------------

const DECISION_LABELS = {
  automatic_positive: "Modulhandbuch",
  needs_review: "Zu prüfen",
  automatic_negative: "Kein Modulhandbuch",
};

async function downloadDoc(jobId, index, filename) {
  const t = getToken();
  const res = await fetch(`/api/scrape/download/${jobId}/${index}`, {
    headers: t ? { "X-Auth-Token": t } : {},
  });
  if (!res.ok) {
    alert("Download fehlgeschlagen.");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "dokument.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function renderClassification(jobId) {
  const card = document.getElementById("sc-classify-card");
  const box = document.getElementById("sc-classify");
  let data;
  try {
    data = await api(`/api/scrape/results/${jobId}`);
  } catch {
    card.style.display = "none";
    return;
  }
  if (!data.available) {
    // Classification off or nothing scored — keep the panel hidden.
    card.style.display = "none";
    return;
  }
  card.style.display = "";

  const c = data.counts || {};
  const summary =
    `<p class="muted">` +
    `${data.relevant.length} relevante Dokument(e) von ${c.total || 0} · ` +
    `${c.automatic_positive || 0} Modulhandbuch, ${c.needs_review || 0} zu prüfen, ` +
    `${c.automatic_negative || 0} aussortiert · ` +
    `${c.reviewed || 0} geprüft</p>` +
    `<p class="muted small">Sichere Treffer (${c.automatic_positive || 0} „Modulhandbuch") ` +
    `sind bereits als positiv vorgewählt — nur Fehler korrigieren. ` +
    `„Zu prüfen"-Dokumente per Download prüfen und markieren, dann unten ` +
    `<strong>Prüfung abschließen</strong> klicken (speichert alle Markierungen ` +
    `gemeinsam). Danach: <code>python -m mlclassifier feedback-retrain --from-s3</code>.</p>`;

  if (data.relevant.length === 0) {
    box.innerHTML = summary + `<p class="muted">Keine relevanten Dokumente gefunden.</p>`;
    return;
  }

  // Client-side selection. Clicking a verdict only *marks* the row; nothing is
  // sent until "Prüfung abschließen" writes the whole batch in one request.
  // Seeding priority per row:
  //   1. a verdict already stored (re-opening a run shows prior choices), else
  //   2. pre-mark confident automatic_positive rows as positive, so you only
  //      override the model's mistakes instead of confirming every 0.85+ by hand.
  //      (Nothing is saved until you click "Prüfung abschließen".)
  selectedVerdicts = {};
  for (const r of data.relevant) {
    if (r.verdict) {
      selectedVerdicts[r.index] = r.verdict;
    } else if (r.decision === "automatic_positive") {
      selectedVerdicts[r.index] = "positive";
    }
  }

  const rows = data.relevant
    .map((r) => {
      const score = r.score === null || r.score === undefined ? "—" : r.score.toFixed(3);
      const label = DECISION_LABELS[r.decision] || r.decision;
      return (
        `<tr>` +
        `<td>${escapeHtml(r.filename)}</td>` +
        `<td><span class="badge badge-${r.decision === "automatic_positive" ? "scraped" : "pending"}">${escapeHtml(label)}</span></td>` +
        `<td class="num">${score}</td>` +
        `<td class="muted small" title="${escapeHtml(r.url)}">${escapeHtml(r.hostname)}</td>` +
        `<td class="verdict-cell">${verdictButtons(r)}</td>` +
        `<td><button class="dl-btn" data-idx="${r.index}" data-name="${escapeHtml(r.filename)}">Download</button></td>` +
        `</tr>`
      );
    })
    .join("");

  box.innerHTML =
    summary +
    `<div class="table-scroll"><table class="result-table">` +
    `<thead><tr><th>Datei</th><th>Klassifikation</th><th>Score</th><th>Quelle</th>` +
    `<th>Prüfung</th><th></th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<div class="review-actions">` +
    `<button id="sc-finish-review" class="finish-btn"></button>` +
    `<span id="sc-review-msg" class="muted small"></span></div>`;

  box.querySelectorAll(".dl-btn").forEach((btn) =>
    btn.addEventListener("click", () =>
      downloadDoc(jobId, Number(btn.dataset.idx), btn.dataset.name)
    )
  );
  box.querySelectorAll(".verdict-btn").forEach((btn) =>
    btn.addEventListener("click", () => selectVerdict(btn))
  );
  document
    .getElementById("sc-finish-review")
    .addEventListener("click", () => finishReview(jobId));
  updateFinishButton();
}

// Two verdict buttons for one row, highlighting the current selection.
function verdictButtons(r) {
  const chosen = selectedVerdicts[r.index];
  const mk = (v) => {
    const active = chosen === v ? ` active-${v === "positive" ? "pos" : "neg"}` : "";
    return (
      `<button class="verdict-btn${active}" data-idx="${r.index}" ` +
      `data-verdict="${v}">${escapeHtml(VERDICT_LABELS[v])}</button>`
    );
  };
  return mk("positive") + mk("negative");
}

// Mark a row's verdict client-side (no network). Toggles off if re-clicked.
function selectVerdict(btn) {
  const idx = Number(btn.dataset.idx);
  const verdict = btn.dataset.verdict;
  const cell = btn.closest(".verdict-cell");
  const buttons = cell.querySelectorAll(".verdict-btn");

  if (selectedVerdicts[idx] === verdict) {
    delete selectedVerdicts[idx]; // toggle off
  } else {
    selectedVerdicts[idx] = verdict;
  }
  buttons.forEach((b) => {
    b.classList.remove("active-pos", "active-neg");
    if (b.dataset.verdict === selectedVerdicts[idx]) {
      b.classList.add(b.dataset.verdict === "positive" ? "active-pos" : "active-neg");
    }
  });
  updateFinishButton();
}

function updateFinishButton() {
  const btn = document.getElementById("sc-finish-review");
  if (!btn) return;
  const n = Object.keys(selectedVerdicts).length;
  btn.textContent = `Prüfung abschließen (${n})`;
  btn.disabled = n === 0;
}

// Send every selected verdict in a single request.
async function finishReview(jobId) {
  const items = Object.entries(selectedVerdicts).map(([index, verdict]) => ({
    index: Number(index),
    verdict,
  }));
  if (items.length === 0) return;

  const btn = document.getElementById("sc-finish-review");
  const msg = document.getElementById("sc-review-msg");
  btn.disabled = true;
  btn.textContent = "Speichern…";
  try {
    const res = await api(`/api/scrape/feedback/${jobId}`, {
      method: "POST",
      body: { items },
    });
    if (res.s3 === false) {
      // Saved in the container but the S3 mirror failed — these won't reach the
      // retrain. Surface it loudly instead of pretending it worked.
      msg.className = "err small";
      msg.textContent =
        `${res.saved} gespeichert, aber S3-Upload fehlgeschlagen — ` +
        `Instanz-Rolle braucht s3:PutObject. Verdicts erreichen das Training noch nicht.`;
    } else {
      msg.className = "muted small";
      msg.textContent = `${res.saved} Verdict(s) gespeichert${
        res.s3 === true ? " (in S3)" : ""
      }. Retrain mit: python -m mlclassifier feedback-retrain --from-s3`;
    }
    await renderClassification(jobId); // refresh counts + persisted state
  } catch (err) {
    msg.className = "err small";
    msg.textContent = "Speichern fehlgeschlagen: " + (err.detail || "Unbekannter Fehler");
    updateFinishButton();
  }
}

function pollStatus(jobId) {
  return new Promise((resolve) => {
    const tick = async () => {
      let job;
      try {
        job = await api(`/api/scrape/status/${jobId}`);
      } catch (err) {
        document.getElementById("sc-results").innerHTML =
          `<p class="err">${escapeHtml(err.detail || "Statusabfrage fehlgeschlagen.")}</p>`;
        document.getElementById("sc-progress").innerHTML = "";
        return resolve(false);
      }
      renderProgress(job);
      if (job.status === "running") {
        setTimeout(tick, 1500);
        return;
      }
      renderResults(job);
      renderClassification(jobId);
      resolve(job.status === "done");
    };
    tick();
  });
}

function setupStart() {
  const btn = document.getElementById("sc-start");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Läuft…";
    showResultCard();
    document.getElementById("sc-classify-card").style.display = "none";
    document.getElementById("sc-progress").innerHTML =
      `<div class="progress-wrap"><div class="progress-bar indeterminate"></div></div>` +
      `<p class="muted">Job wird gestartet …</p>`;
    document.getElementById("sc-results").innerHTML = "";
    try {
      const fd = new FormData();
      fd.append("file_types", selectedFileTypes().join(","));
      const modelId = document.getElementById("sc-model").value;
      if (modelId) fd.append("model_id", modelId); // optional bis Modell existiert
      fd.append("url", document.getElementById("sc-url").value.trim());
      const fileInput = document.getElementById("sc-file");
      if (fileInput.files.length) fd.append("file", fileInput.files[0]);

      const started = await apiForm("/api/scrape", fd);
      await pollStatus(started.job_id);
    } catch (err) {
      document.getElementById("sc-progress").innerHTML = "";
      document.getElementById("sc-results").innerHTML =
        `<p class="err">${escapeHtml(err.detail || "Scrape fehlgeschlagen.")}</p>`;
    } finally {
      btn.textContent = original;
      await loadLog();
      updateButtonState();
    }
  });
}

export async function initScrapeSection() {
  document.getElementById("sc-url").addEventListener("input", updateButtonState);
  document.getElementById("sc-file").addEventListener("change", updateButtonState);
  document.getElementById("sc-model").addEventListener("change", updateButtonState);
  setupStart();
  await loadFileTypes();
  await loadModels();
  await loadLog();
  updateButtonState();
}
