(function () {
  const TOKEN_KEY = "bp_token";

  function getToken() {
    try {
      return window.localStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  }

  function setToken(token) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token || "");
    } catch {
      // ignore
    }
  }

  function clearToken() {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore
    }
  }

  function toast(message, type = "info") {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.dataset.type = type;
    el.classList.add("is-visible");
    window.clearTimeout(toast._t);
    toast._t = window.setTimeout(() => el.classList.remove("is-visible"), 3200);
  }

  async function apiFetch(path, options) {
    const opts = options ? { ...options } : {};
    opts.headers = opts.headers ? { ...opts.headers } : {};
    const token = getToken();
    if (token) opts.headers.Authorization = `Bearer ${token}`;
    return fetch(path, opts);
  }

  async function fetchJson(path, options) {
    const res = await apiFetch(path, options);
    if (res.status === 401) {
      clearToken();
      if (!String(window.location.pathname || "").startsWith("/login")) {
        window.location.href = "/login";
      }
      throw new Error("Ворид нашудаед.");
    }
    if (!res.ok) {
      const raw = await res.text().catch(() => "");
      try {
        const parsed = JSON.parse(raw);
        const detail = parsed?.detail || raw || res.statusText;
        throw new Error(String(detail || "Хатои дархост"));
      } catch {
        throw new Error(String(raw || res.statusText || "Хатои дархост"));
      }
    }
    return res.json();
  }

  async function fetchBlob(path, options) {
    const res = await apiFetch(path, options);
    if (res.status === 401) {
      clearToken();
      window.location.href = "/login";
      throw new Error("Ворид нашудаед.");
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(String(text || res.statusText || "Хатои дархост"));
    }
    return res.blob();
  }

  function requireAuthOrRedirect() {
    if (!getToken()) {
      window.location.href = "/login";
      return false;
    }
    return true;
  }

  async function me() {
    return fetchJson("/auth/me");
  }

  function logout() {
    clearToken();
    window.location.href = "/login";
  }

  window.Auth = {
    getToken,
    setToken,
    clearToken,
    toast,
    fetchJson,
    fetchBlob,
    requireAuthOrRedirect,
    me,
    logout,
  };
})();
