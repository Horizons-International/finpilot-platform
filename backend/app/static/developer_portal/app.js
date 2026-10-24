(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const DEFAULT_BASE = window.location.origin;
  let adminAccessToken = null;
  let lastCreatedSecret = "";

  const baseInput = byId("api-base-url");
  baseInput.value = DEFAULT_BASE;
  byId("base-url-label").textContent = DEFAULT_BASE;

  function apiBase() {
    const raw = baseInput.value.trim() || DEFAULT_BASE;
    const url = new URL(raw);
    if (!new Set(["http:", "https:"]).has(url.protocol)) {
      throw new Error("The API base URL must use HTTP or HTTPS.");
    }
    return url.toString().replace(/\/$/, "");
  }

  function htmlEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function formatTimestamp(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  async function readResponse(response) {
    const text = await response.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch { return text; }
  }

  function pretty(value) {
    return typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  async function requestJson(path, options = {}) {
    const url = `${apiBase()}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: { ...(options.headers || {}) },
      credentials: "omit",
      cache: "no-store",
    });
    const body = await readResponse(response);
    if (!response.ok) {
      const message = body && typeof body === "object" ? (body.message || body.detail || response.statusText) : (body || response.statusText);
      throw new Error(`${response.status} ${response.statusText}: ${message}`);
    }
    return body;
  }

  async function updateEnvironment() {
    try {
      const base = apiBase();
      byId("base-url-label").textContent = base;
      const result = await requestJson("/health");
      const environment = result?.data?.environment;
      const version = result?.data?.version;
      byId("environment-label").textContent = [environment, version ? `v${version}` : ""].filter(Boolean).join(" · ") || "current API deployment";
    } catch {
      byId("environment-label").textContent = "environment not detected";
    }
  }

  baseInput.addEventListener("change", updateEnvironment);
  updateEnvironment();

  // Highlight the section currently being viewed.
  const navLinks = Array.from(document.querySelectorAll("#side-nav .nav-link"));
  const sectionObserver = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    navLinks.forEach((link) => link.classList.toggle("active", link.hash === `#${visible.target.id}`));
  }, { rootMargin: "-12% 0px -75% 0px", threshold: [0, 0.2, 0.5] });
  document.querySelectorAll("main section[id]").forEach((section) => sectionObserver.observe(section));

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = "Copied";
      } catch {
        button.textContent = "Select path above";
      }
      window.setTimeout(() => { button.textContent = original; }, 1400);
    });
  });

  // The method and path shortcuts are helpers for the request playground.
  document.querySelectorAll("[data-try-path]").forEach((button) => {
    button.addEventListener("click", () => {
      byId("request-path").value = button.dataset.tryPath;
      byId("request-method").value = button.dataset.method || "GET";
      byId("request-auth").value = button.dataset.auth || "none";
      byId("request-credential").value = "";
      byId("request-body").value = button.dataset.method === "POST" ? "{}" : "";
      byId("sandbox").scrollIntoView({ behavior: "smooth" });
      byId("request-path").focus({ preventScroll: true });
    });
  });

  byId("reset-request").addEventListener("click", () => {
    byId("request-method").value = "GET";
    byId("request-path").value = "/health";
    byId("request-auth").value = "none";
    byId("request-credential").value = "";
    byId("request-body").value = "";
    byId("request-status").textContent = "";
    byId("response-meta").textContent = "No request sent";
    byId("response-output").innerHTML = "<code>Response JSON will appear here.</code>";
  });

  byId("send-request").addEventListener("click", async () => {
    const button = byId("send-request");
    const statusEl = byId("request-status");
    const output = byId("response-output").querySelector("code");
    const method = byId("request-method").value;
    const path = byId("request-path").value.trim();
    const authType = byId("request-auth").value;
    const credential = byId("request-credential").value.trim();
    const bodyText = byId("request-body").value.trim();

    if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
      statusEl.textContent = "Use a relative path beginning with one slash, such as /health.";
      return;
    }

    let target;
    try {
      target = new URL(path, `${apiBase()}/`);
      if (target.origin !== new URL(apiBase()).origin) throw new Error("Path must stay on the selected API origin.");
    } catch (error) {
      statusEl.textContent = error instanceof Error ? error.message : "Invalid API URL.";
      return;
    }

    const headers = { Accept: "application/json" };
    if (authType === "jwt") {
      if (!credential) { statusEl.textContent = "Enter a JWT access token, or choose no authentication."; return; }
      headers.Authorization = `Bearer ${credential}`;
    }
    if (authType === "api-key") {
      if (!credential) { statusEl.textContent = "Enter an API key, or choose no authentication."; return; }
      headers["X-API-Key"] = credential;
    }

    const options = { method, headers };
    if (["POST", "PUT", "PATCH"].includes(method) && bodyText) {
      try { options.body = JSON.stringify(JSON.parse(bodyText)); }
      catch { statusEl.textContent = "Request body must be valid JSON."; return; }
      headers["Content-Type"] = "application/json";
    }

    button.disabled = true;
    statusEl.textContent = "Request in progress…";
    byId("response-meta").textContent = "Waiting for response";
    output.textContent = "Loading…";
    const started = performance.now();
    try {
      const response = await fetch(target.toString(), { ...options, credentials: "omit", cache: "no-store" });
      const responseBody = await readResponse(response);
      byId("response-meta").textContent = `${response.status} ${response.statusText} · ${Math.round(performance.now() - started)} ms`;
      output.textContent = pretty(responseBody);
      statusEl.textContent = response.ok ? "Request completed." : "The API returned an error; inspect the response.";
    } catch (error) {
      byId("response-meta").textContent = "Request failed";
      output.textContent = error instanceof Error ? error.message : String(error);
      statusEl.textContent = "Network error. Confirm the base URL, server status, TLS, and CORS settings.";
    } finally {
      button.disabled = false;
    }
  });

  // API key manager. Tokens are deliberately held in memory only, not localStorage.
  function setKeyStatus(message, isError = false) {
    const el = byId("key-management-status");
    el.textContent = message;
    el.classList.toggle("is-error", isError);
  }

  function setLoginStatus(message, isError = false) {
    const el = byId("key-login-status");
    el.textContent = message;
    el.classList.toggle("is-error", isError);
  }

  async function adminRequest(path, options = {}) {
    if (!adminAccessToken) throw new Error("Please sign in first.");
    const headers = { Authorization: `Bearer ${adminAccessToken}`, ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    return requestJson(path, { ...options, headers });
  }

  async function loadKeys() {
    const result = await adminRequest("/api/v1/api-keys");
    const keys = result?.data;
    if (!Array.isArray(keys)) throw new Error("Unexpected API-key list response.");
    const tbody = byId("keys-table-body");
    if (!keys.length) {
      tbody.innerHTML = '<tr><td colspan="6">No keys found for this tenant.</td></tr>';
      return;
    }
    tbody.innerHTML = keys.map((key) => `<tr>
      <td><strong>${htmlEscape(key.name)}</strong></td>
      <td>${htmlEscape(key.status)}</td>
      <td>${htmlEscape(Array.isArray(key.permissions) ? key.permissions.join(", ") : "")}</td>
      <td>${htmlEscape(formatTimestamp(key.created_at))}</td>
      <td>${htmlEscape(formatTimestamp(key.last_used_at))}</td>
      <td>${key.status === "ACTIVE" ? `<button class="row-action danger" data-revoke-key="${htmlEscape(key.id)}" data-key-name="${htmlEscape(key.name)}">Revoke</button>` : "—"}<button class="row-action" data-usage-key="${htmlEscape(key.id)}">Usage</button></td>
    </tr>`).join("");
    tbody.querySelectorAll("[data-revoke-key]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.revokeKey;
        const name = button.dataset.keyName || "this key";
        if (!window.confirm(`Revoke API key “${name}”? Existing integrations using it will stop working.`)) return;
        button.disabled = true;
        try {
          await adminRequest(`/api/v1/api-keys/${encodeURIComponent(id)}/revoke`, { method: "POST" });
          setKeyStatus(`Revoked “${name}”.`);
          await loadKeys();
        } catch (error) { setKeyStatus(error.message, true); button.disabled = false; }
      });
    });
    tbody.querySelectorAll("[data-usage-key]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.usageKey;
        const usagePanel = byId("key-usage-panel");
        const usageBody = byId("key-usage-body");
        button.disabled = true;
        try {
          const usageResult = await adminRequest(`/api/v1/api-keys/${encodeURIComponent(id)}/usage?limit=100`);
          const usage = usageResult?.data;
          if (!Array.isArray(usage)) throw new Error("Unexpected API-key usage response.");
          usageBody.innerHTML = usage.length ? usage.map((row) => `<tr><td>${htmlEscape(formatTimestamp(row.created_at))}</td><td>${htmlEscape(row.method)}</td><td>${htmlEscape(row.path)}</td><td>${htmlEscape(row.status_code)}</td><td>${htmlEscape(row.request_id || "—")}</td></tr>`).join("") : '<tr><td colspan="5">No recorded usage for this key.</td></tr>';
          usagePanel.hidden = false;
          setKeyStatus(`Loaded ${usage.length} usage record(s).`);
        } catch (error) { setKeyStatus(error.message, true); }
        finally { button.disabled = false; }
      });
    });
  }

  byId("key-login-button").addEventListener("click", async () => {
    const button = byId("key-login-button");
    const email = byId("key-login-email").value.trim();
    const password = byId("key-login-password").value;
    const mfaCode = byId("key-login-mfa").value.trim();
    if (!email || !password) { setLoginStatus("Enter your email and password.", true); return; }
    button.disabled = true;
    setLoginStatus("Signing in…");
    try {
      const result = await requestJson("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email, password, ...(mfaCode ? { mfa_code: mfaCode } : {}) }),
      });
      const token = result?.data?.access_token;
      if (typeof token !== "string" || !token) throw new Error("The login response did not contain an access token.");
      adminAccessToken = token;
      byId("key-login-password").value = "";
      byId("key-login-mfa").value = "";
      byId("key-login-panel").hidden = true;
      byId("key-management-panel").hidden = false;
      byId("key-usage-panel").hidden = true;
      setKeyStatus("Signed in. Loading keys…");
      await loadKeys();
      setKeyStatus("Keys loaded.");
    } catch (error) {
      adminAccessToken = null;
      byId("key-login-password").value = "";
      byId("key-login-panel").hidden = false;
      byId("key-management-panel").hidden = true;
      setLoginStatus(error instanceof Error ? error.message : String(error), true);
    } finally { button.disabled = false; }
  });

  byId("key-logout-button").addEventListener("click", () => {
    adminAccessToken = null;
    lastCreatedSecret = "";
    byId("key-login-password").value = "";
    byId("key-login-mfa").value = "";
    byId("key-login-panel").hidden = false;
    byId("key-management-panel").hidden = true;
    byId("new-key-secret").hidden = true;
    byId("keys-table-body").innerHTML = '<tr><td colspan="6">Sign in to list keys.</td></tr>';
    byId("key-usage-panel").hidden = true;
    setLoginStatus("Signed out. The access token was cleared from this page.");
  });

  byId("create-key-button").addEventListener("click", async () => {
    const button = byId("create-key-button");
    const name = byId("new-key-name").value.trim();
    const permissionsText = byId("new-key-permissions").value.trim();
    const permissions = [...new Set(permissionsText.split(",").map((part) => part.trim().toLowerCase()).filter(Boolean))];
    if (!name) { setKeyStatus("Enter a name for the new key.", true); return; }
    if (!permissions.length || permissions.some((item) => !/^[a-z][a-z0-9_-]*:(read|write|create|update|delete)$/.test(item))) {
      setKeyStatus("Each permission must look like customers:read, integrations:write, etc.", true); return;
    }
    button.disabled = true;
    setKeyStatus("Creating key…");
    try {
      const result = await adminRequest("/api/v1/api-keys", { method: "POST", body: JSON.stringify({ name, permissions }) });
      const keyData = result?.data;
      if (!keyData || typeof keyData.api_key !== "string") throw new Error("The response did not contain the one-time API key secret.");
      lastCreatedSecret = keyData.api_key;
      byId("new-key-value").textContent = keyData.api_key;
      byId("new-key-secret").hidden = false;
      setKeyStatus("API key created. Copy and store the secret securely; it will not be shown again.");
      await loadKeys();
    } catch (error) { setKeyStatus(error instanceof Error ? error.message : String(error), true); }
    finally { button.disabled = false; }
  });

  byId("copy-new-key").addEventListener("click", async () => {
    if (!lastCreatedSecret) { setKeyStatus("No new key secret is available to copy.", true); return; }
    try {
      await navigator.clipboard.writeText(lastCreatedSecret);
      byId("copy-new-key").textContent = "Copied";
      window.setTimeout(() => { byId("copy-new-key").textContent = "Copy secret"; }, 1400);
    } catch { setKeyStatus("Clipboard access was denied. Select and copy the secret manually.", true); }
  });
})();
