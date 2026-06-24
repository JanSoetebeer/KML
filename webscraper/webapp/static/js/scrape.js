// Section "Scraping" (Abschnitt 1).
import { api, apiForm } from "./api.js";

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
  if (!model) reasons.push("KI-Modell");
  if (!hasSource()) reasons.push("URL oder Datei");

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

function setupStart() {
  const btn = document.getElementById("sc-start");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Läuft…";
    try {
      const fd = new FormData();
      fd.append("file_types", selectedFileTypes().join(","));
      fd.append("model_id", document.getElementById("sc-model").value);
      fd.append("url", document.getElementById("sc-url").value.trim());
      const fileInput = document.getElementById("sc-file");
      if (fileInput.files.length) fd.append("file", fileInput.files[0]);

      await apiForm("/api/scrape", fd);
    } catch (err) {
      alert(err.detail || "Scrape fehlgeschlagen.");
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
