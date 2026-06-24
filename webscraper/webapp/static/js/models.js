// Section "KI-Modelle" (Abschnitt 3) — admin only.
import { api, apiForm } from "./api.js";

function showNote(el, message, ok = true) {
  el.textContent = message;
  el.classList.remove("success", "error");
  el.classList.add("show", ok ? "success" : "error");
}
function hideNote(el) {
  el.classList.remove("show");
}

async function loadModelSelect() {
  const data = await api("/api/models");
  const select = document.getElementById("md-select");
  select.innerHTML = "";
  if (data.models.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "(keine Modelle)";
    select.appendChild(opt);
  } else {
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.bezeichnung;
      select.appendChild(opt);
    }
  }
}

async function loadMatrix() {
  const data = await api("/api/models/matrix");
  const table = document.getElementById("matrix-table");
  const empty = document.getElementById("matrix-empty");

  if (data.models.length === 0) {
    table.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  const assigned = new Set(data.assignments.map(([m, r]) => `${m}:${r}`));

  // header row: corner + role names
  let html = "<thead><tr><th>Modell \\ Rolle</th>";
  for (const role of data.roles) {
    html += `<th>${escapeHtml(role.bezeichnung)}</th>`;
  }
  html += "</tr></thead><tbody>";

  for (const model of data.models) {
    html += `<tr><th class="row-head">${escapeHtml(model.bezeichnung)}</th>`;
    for (const role of data.roles) {
      const checked = assigned.has(`${model.id}:${role.id}`) ? "checked" : "";
      html +=
        `<td><input type="checkbox" data-model="${model.id}" ` +
        `data-role="${role.id}" ${checked} /></td>`;
    }
    html += "</tr>";
  }
  html += "</tbody>";
  table.innerHTML = html;

  table.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", async () => {
      try {
        await api("/api/models/matrix", {
          method: "POST",
          body: {
            model_id: Number(cb.dataset.model),
            role_id: Number(cb.dataset.role),
            assigned: cb.checked,
          },
        });
      } catch (err) {
        cb.checked = !cb.checked; // revert on failure
        alert(err.detail || "Aktualisierung fehlgeschlagen.");
      }
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setupUpload() {
  const fileInput = document.getElementById("mu-file");
  const note = document.getElementById("mu-note");
  document.getElementById("mu-upload").addEventListener("click", async () => {
    hideNote(note);
    if (!fileInput.files.length) {
      showNote(note, "Bitte zuerst eine Datei auswählen.", false);
      return;
    }
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    try {
      const m = await apiForm("/api/models", fd);
      showNote(note, `Modell "${m.bezeichnung}" wurde hochgeladen.`, true);
      fileInput.value = "";
      await loadMatrix();
      await loadModelSelect();
    } catch (err) {
      showNote(note, err.detail || "Upload fehlgeschlagen.", false);
    }
  });
}

function setupDelete() {
  const select = document.getElementById("md-select");
  const note = document.getElementById("md-note");
  document.getElementById("md-delete").addEventListener("click", async () => {
    hideNote(note);
    if (!select.value) {
      showNote(note, "Bitte ein Modell wählen.", false);
      return;
    }
    const name = select.options[select.selectedIndex].textContent;

    // Double confirmation, as specified.
    if (!confirm(`Modell "${name}" wirklich löschen?`)) return;
    if (!confirm(`Sind Sie sicher? "${name}" wird endgültig gelöscht.`)) return;

    try {
      await api(`/api/models/${select.value}`, { method: "DELETE" });
      showNote(note, `Modell "${name}" wurde gelöscht.`, true);
      await loadMatrix();
      await loadModelSelect();
    } catch (err) {
      showNote(note, err.detail || "Löschen fehlgeschlagen.", false);
    }
  });
}

export async function initModelsSection(state) {
  if (!state.user.is_admin) return;
  setupUpload();
  setupDelete();
  await loadMatrix();
  await loadModelSelect();
}

// Allow other sections (e.g. role creation) to refresh the matrix columns.
export { loadMatrix };
