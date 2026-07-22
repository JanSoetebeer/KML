import { api, clearToken, getToken } from "./api.js";
import { initUsersSection } from "./users.js";
import { initModelsSection } from "./models.js";
import { initScrapeSection } from "./scrape.js";

// Shared application state, populated on load.
export const state = {
  user: null, // {id, username, position, is_admin, roles:[...]}
};

const usernameEl = document.getElementById("current-username");
const positionEl = document.getElementById("current-position");
const logoutBtn = document.getElementById("logout-btn");

function logout() {
  clearToken();
  window.location.href = "/login";
}

logoutBtn.addEventListener("click", logout);

// ---- Tab navigation ----
function setupTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
    });
  });
}

// ---- Visibility based on position ----
function applyVisibility() {
  const isAdmin = state.user.is_admin;
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", !isAdmin);
  });
  // If a non-admin somehow has the models tab active, switch to scraping.
  if (!isAdmin) {
    const modelsBtn = document.querySelector('[data-tab="tab-models"]');
    if (modelsBtn && modelsBtn.classList.contains("active")) {
      document.querySelector('[data-tab="tab-scrape"]').click();
    }
  }
}

function renderUser() {
  usernameEl.textContent = state.user.username;
  positionEl.textContent = state.user.position;
}

// ---- Bootstrap ----
(async function init() {
  if (!getToken()) {
    window.location.href = "/login";
    return;
  }
  try {
    const data = await api("/api/auth/me");
    state.user = data.user;
  } catch {
    logout();
    return;
  }
  renderUser();
  setupTabs();
  applyVisibility();
  await initUsersSection(state);
  await initModelsSection(state);
  await initScrapeSection(state);
})();
