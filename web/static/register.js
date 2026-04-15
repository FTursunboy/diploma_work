(function () {
  const form = document.getElementById("registerForm");
  const emailEl = document.getElementById("email");
  const passwordEl = document.getElementById("password");
  const btn = document.getElementById("registerBtn");

  if (!form) return;

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
      const data = await Auth.fetchJson("/auth/register", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      Auth.setToken(data?.access_token || "");
      Auth.toast("Ҳисоб эҷод шуд.", "success");
      window.location.href = "/";
    } catch (err) {
      Auth.toast(String(err?.message || err || "Хатои бақайдгирӣ"), "error");
    } finally {
      setBusy(false, "Эҷод кардан");
    }
  });
})();
