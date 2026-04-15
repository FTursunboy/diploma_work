(function () {
  if (!Auth.requireAuthOrRedirect()) return;

  const els = {
    userBadge: document.getElementById("userBadge"),
    logoutBtn: document.getElementById("logoutBtn"),
    usersMeta: document.getElementById("usersMeta"),
    tbody: document.getElementById("usersTbody"),
    adminError: document.getElementById("adminError"),
  };

  let me = null;
  let users = [];

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function setError(message) {
    if (!els.adminError) return;
    els.adminError.style.display = "";
    els.adminError.textContent = message;
  }

  function setUserNav() {
    if (els.userBadge) {
      els.userBadge.style.display = "";
      const who = me.email || me.username || "—";
      const role = String(me.role || "");
      const roleLabel = role === "admin" ? "админ" : role === "moderator" ? "модератор" : "корбар";
      els.userBadge.textContent = `${who} • ${roleLabel}`;
    }
    if (els.logoutBtn) {
      els.logoutBtn.style.display = "";
      els.logoutBtn.addEventListener("click", () => Auth.logout());
    }
  }

  function updateMeta() {
    if (els.usersMeta) els.usersMeta.textContent = `${users.length} корбар`;
  }

  function roleOptions(selected) {
    const roles = [
      { value: "user", label: "корбар" },
      { value: "moderator", label: "модератор" },
      { value: "admin", label: "админ" },
    ];
    return roles
      .map((r) => `<option value="${r.value}" ${r.value === selected ? "selected" : ""}>${r.label}</option>`)
      .join("");
  }

  function renderUsers() {
    if (!els.tbody) return;
    els.tbody.innerHTML = "";

    for (const u of users) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${escapeHtml(u.id)}</td>
        <td>${escapeHtml(u.email || u.username || "")}</td>
        <td>
          <select class="select select--sm" data-role="${escapeHtml(u.id)}">
            ${roleOptions(u.role)}
          </select>
        </td>
        <td class="td--actions">
          <button class="btn btn--sm" data-save="${escapeHtml(u.id)}">Нигоҳ доштан</button>
        </td>
      `;
      els.tbody.appendChild(tr);
    }

    for (const btn of els.tbody.querySelectorAll("[data-save]")) {
      btn.addEventListener("click", () => onSave(btn.getAttribute("data-save")));
    }
  }

  async function refreshUsers() {
    users = await Auth.fetchJson("/admin/users");
    if (!Array.isArray(users)) users = [];
    updateMeta();
    renderUsers();
  }

  async function onSave(userIdRaw) {
    const userId = Number(userIdRaw || 0);
    if (!userId) return;

    const select = document.querySelector(`[data-role="${CSS.escape(String(userId))}"]`);
    const btn = document.querySelector(`[data-save="${CSS.escape(String(userId))}"]`);
    if (!select || !btn) return;

    const role = String(select.value || "").trim();
    btn.disabled = true;
    btn.textContent = "…";
    try {
      await Auth.fetchJson(`/admin/users/${userId}/role`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role }),
      });
      Auth.toast("Нақш нав шуд.", "success");
      await refreshUsers();
    } catch (err) {
      Auth.toast(String(err?.message || err || "Нақш нав нашуд"), "error");
      btn.disabled = false;
      btn.textContent = "Нигоҳ доштан";
    }
  }

  async function init() {
    try {
      me = await Auth.me();
      setUserNav();
      if (me.role !== "admin") {
        setError("Дастрасӣ нест: нақши admin лозим аст.");
        return;
      }
      await refreshUsers();
    } catch (err) {
      setError(String(err?.message || err || "Хато"));
    }
  }

  init();
})();
