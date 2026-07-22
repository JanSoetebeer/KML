import { api, getToken, setToken } from "./api.js";

const form = document.getElementById("login-form");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const notification = document.getElementById("notification");
const loginBtn = document.getElementById("login-btn");

function showError(message) {
  notification.textContent = message;
  notification.classList.add("show");
}
function hideError() {
  notification.classList.remove("show");
}

// On load: if a valid token already exists, redirect straight to the app.
(async function autoRedirect() {
  const token = getToken();
  if (!token) return;
  try {
    await api("/api/auth/validate", { method: "POST", auth: false, body: { token } });
    window.location.href = "/app";
  } catch {
    // invalid/stale token — stay on login page
  }
})();

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  loginBtn.disabled = true;

  const username = usernameInput.value;
  const password = passwordInput.value;

  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      auth: false,
      body: { username, password },
    });
    setToken(data.token);
    window.location.href = "/app";
  } catch (err) {
    // Invalid credentials: clear fields + show notification
    usernameInput.value = "";
    passwordInput.value = "";
    showError(err.detail || "Die Anmeldedaten sind falsch.");
    usernameInput.focus();
  } finally {
    loginBtn.disabled = false;
  }
});
