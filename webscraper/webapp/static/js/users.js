// Section "Benutzerverwaltung" (Abschnitt 2).
import { api, setToken } from "./api.js";

let cachedRoles = [];

function showNote(el, message, ok = true) {
  el.textContent = message;
  el.classList.remove("success", "error");
  el.classList.add("show", ok ? "success" : "error");
}
function hideNote(el) {
  el.classList.remove("show");
}

function fillSelect(select, items, { placeholder = null } = {}) {
  select.innerHTML = "";
  if (placeholder !== null) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder;
    select.appendChild(opt);
  }
  for (const it of items) {
    const opt = document.createElement("option");
    opt.value = it.id;
    opt.textContent = it.bezeichnung || it.username;
    select.appendChild(opt);
  }
}

async function loadRoles() {
  const data = await api("/api/roles");
  cachedRoles = data.roles;
  fillSelect(document.getElementById("cu-role"), cachedRoles, {
    placeholder: "(keine Rolle)",
  });
}

async function loadUsers() {
  const data = await api("/api/users");
  fillSelect(document.getElementById("ru-user"), data.users, {
    placeholder: "Bitte wählen…",
  });
}

// ---- Create user ----
function setupCreateUser() {
  const username = document.getElementById("cu-username");
  const password = document.getElementById("cu-password");
  const isAdmin = document.getElementById("cu-admin");
  const role = document.getElementById("cu-role");
  const note = document.getElementById("cu-note");

  function clearForm() {
    username.value = "";
    password.value = "";
    isAdmin.checked = false;
    role.selectedIndex = 0;
    hideNote(note);
  }

  document.getElementById("cu-discard").addEventListener("click", clearForm);

  document.getElementById("cu-create").addEventListener("click", async () => {
    hideNote(note);
    const body = {
      username: username.value,
      password: password.value,
      is_admin: isAdmin.checked,
      role_id: role.value ? Number(role.value) : null,
    };
    try {
      const created = await api("/api/users", { method: "POST", body });
      showNote(note, `Benutzer "${created.username}" wurde angelegt.`, true);
      clearForm();
      await loadUsers();
    } catch (err) {
      // Validation conditions -> messagebox, as specified
      if (err.status === 400) {
        alert(
          "Der Benutzer konnte nicht angelegt werden.\n\n" +
            "Bedingungen:\n" +
            "• Benutzername mindestens 4 Zeichen\n" +
            "• Passwort mindestens 8 Zeichen\n\n" +
            err.detail
        );
      } else {
        showNote(note, err.detail || "Fehler beim Anlegen.", false);
      }
    }
  });
}

// ---- Create role ----
function setupCreateRole() {
  const name = document.getElementById("cr-name");
  const note = document.getElementById("cr-note");

  document.getElementById("cr-discard").addEventListener("click", () => {
    name.value = "";
    hideNote(note);
  });

  document.getElementById("cr-create").addEventListener("click", async () => {
    hideNote(note);
    if (!name.value.trim()) {
      showNote(note, "Bitte eine Bezeichnung eingeben.", false);
      return;
    }
    try {
      const res = await api("/api/roles", {
        method: "POST",
        body: { bezeichnung: name.value },
      });
      if (res.created) {
        showNote(note, `Rolle "${res.role.bezeichnung}" wurde angelegt.`, true);
      } else {
        showNote(note, `Die Rolle "${res.role.bezeichnung}" existiert bereits.`, false);
      }
      name.value = "";
      await loadRoles();
      await refreshAddRoleOptions();
    } catch (err) {
      showNote(note, err.detail || "Fehler beim Anlegen.", false);
    }
  });
}

// ---- Manage user roles ----
let currentUserRoles = [];

async function renderUserRoles() {
  const userSelect = document.getElementById("ru-user");
  const list = document.getElementById("ru-roles");
  const userId = userSelect.value;
  if (!userId) {
    list.innerHTML = '<li class="muted">Bitte Benutzer wählen.</li>';
    currentUserRoles = [];
    await refreshAddRoleOptions();
    return;
  }
  const data = await api(`/api/users/${userId}/roles`);
  currentUserRoles = data.roles;
  if (currentUserRoles.length === 0) {
    list.innerHTML = '<li class="muted">Keine Rollen zugewiesen.</li>';
  } else {
    list.innerHTML = "";
    for (const r of currentUserRoles) {
      const li = document.createElement("li");
      li.textContent = r.bezeichnung + " ";
      const btn = document.createElement("button");
      btn.className = "danger";
      btn.textContent = "Entfernen";
      btn.addEventListener("click", async () => {
        await api(`/api/users/${userId}/roles/${r.id}`, { method: "DELETE" });
        await renderUserRoles();
      });
      li.appendChild(btn);
      list.appendChild(li);
    }
  }
  await refreshAddRoleOptions();
}

async function refreshAddRoleOptions() {
  const addSelect = document.getElementById("ru-add-role");
  const assignedIds = new Set(currentUserRoles.map((r) => r.id));
  const available = cachedRoles.filter((r) => !assignedIds.has(r.id));
  fillSelect(addSelect, available, { placeholder: "Bitte wählen…" });
}

function setupManageRoles() {
  const userSelect = document.getElementById("ru-user");
  const addSelect = document.getElementById("ru-add-role");
  const note = document.getElementById("ru-note");

  userSelect.addEventListener("change", () => {
    hideNote(note);
    renderUserRoles();
  });

  document.getElementById("ru-add").addEventListener("click", async () => {
    hideNote(note);
    const userId = userSelect.value;
    if (!userId) {
      showNote(note, "Bitte zuerst einen Benutzer wählen.", false);
      return;
    }
    if (!addSelect.value) {
      showNote(note, "Bitte eine Rolle wählen.", false);
      return;
    }
    await api(`/api/users/${userId}/roles`, {
      method: "POST",
      body: { role_id: Number(addSelect.value) },
    });
    await renderUserRoles();
    showNote(note, "Rolle hinzugefügt.", true);
  });
}

// ---- Change own password ----
function setupChangePassword() {
  const current = document.getElementById("pw-current");
  const pwNew = document.getElementById("pw-new");
  const confirm = document.getElementById("pw-confirm");
  const note = document.getElementById("pw-note");

  document.getElementById("pw-update").addEventListener("click", async () => {
    hideNote(note);
    if (pwNew.value !== confirm.value) {
      showNote(note, "Das neue Passwort stimmt in beiden Feldern nicht überein.", false);
      return;
    }
    try {
      const res = await api("/api/users/me/password", {
        method: "POST",
        body: { current: current.value, new: pwNew.value, confirm: confirm.value },
      });
      // Token embedded the old password -> replace it so we stay logged in.
      if (res.token) setToken(res.token);
      current.value = "";
      pwNew.value = "";
      confirm.value = "";
      showNote(note, "Passwort wurde aktualisiert.", true);
    } catch (err) {
      showNote(note, err.detail || "Fehler beim Aktualisieren.", false);
    }
  });
}

export async function initUsersSection(state) {
  setupChangePassword(); // visible to everyone

  if (!state.user.is_admin) return; // admin-only parts below

  setupCreateUser();
  setupCreateRole();
  setupManageRoles();
  await loadRoles();
  await loadUsers();
  await refreshAddRoleOptions();
}
