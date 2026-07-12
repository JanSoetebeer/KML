// Section "Scraping" (Abschnitt 1).
import { api, apiForm, getToken } from "./api.js";

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
    `${c.automatic_negative || 0} aussortiert</p>`;

  if (data.relevant.length === 0) {
    box.innerHTML = summary + `<p class="muted">Keine relevanten Dokumente gefunden.</p>`;
    return;
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
        `<td><button class="dl-btn" data-idx="${r.index}" data-name="${escapeHtml(r.filename)}">Download</button></td>` +
        `</tr>`
      );
    })
    .join("");

  box.innerHTML =
    summary +
    `<div class="table-scroll"><table class="result-table">` +
    `<thead><tr><th>Datei</th><th>Klassifikation</th><th>Score</th><th>Quelle</th><th></th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>`;

  box.querySelectorAll(".dl-btn").forEach((btn) =>
    btn.addEventListener("click", () =>
      downloadDoc(jobId, Number(btn.dataset.idx), btn.dataset.name)
    )
  );
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
