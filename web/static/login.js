(function () {
  const form = document.getElementById("loginForm");
  const emailEl = document.getElementById("email");
  const passwordEl = document.getElementById("password");
  const btn = document.getElementById("loginBtn");

  if (!form) return;

  if (Auth.getToken()) {
    Auth.me()
      .then((u) => {
        if (u?.role === "user") window.location.href = "/viewer";
        else window.location.href = "/";
      })
      .catch(() => {
        Auth.clearToken();
      });
  }

  function setBusy(busy, label) {
    btn.disabled = !!busy;
    if (label) btn.textContent = label;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = String(emailEl.value || "").trim();
    const password = String(passwordEl.value || "");
    if (!email || !password) return;

    setBusy(true, "…");
    try {
      const data = await Auth.fetchJson("/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      Auth.setToken(data?.access_token || "");
      const role = data?.user?.role || "";
      Auth.toast("Ворид шудед.", "success");
      window.location.href = role === "user" ? "/viewer" : "/";
    } catch (err) {
      Auth.toast(String(err?.message || err || "Хатои воридшавӣ"), "error");
    } finally {
      setBusy(false, "Даромадан");
    }
  });
})();
