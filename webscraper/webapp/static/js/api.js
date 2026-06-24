// Shared API helper + token storage (used by login.js and app.js).

const TOKEN_KEY = "auth_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Call a JSON API endpoint.
 * @param {string} path
 * @param {{method?: string, body?: any, auth?: boolean}} opts
 */
export async function api(path, { method = "GET", body = null, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers["X-Auth-Token"] = t;
  }
  const res = await fetch(path, {
    method,
    headers,
    body: body !== null ? JSON.stringify(body) : null,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw { status: res.status, detail: err.detail || "Unbekannter Fehler" };
  }
  if (res.status === 204) return null;
  return res.json();
}

/** Upload form data (e.g. file uploads) with auth header. */
export async function apiForm(path, formData) {
  const headers = {};
  const t = getToken();
  if (t) headers["X-Auth-Token"] = t;
  const res = await fetch(path, { method: "POST", headers, body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw { status: res.status, detail: err.detail || "Unbekannter Fehler" };
  }
  return res.status === 204 ? null : res.json();
}
