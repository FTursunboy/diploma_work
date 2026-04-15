(function () {
  if (!Auth.requireAuthOrRedirect()) return;

  const els = {
    userBadge: document.getElementById("userBadge"),
    logoutBtn: document.getElementById("logoutBtn"),
    adminMeta: document.getElementById("adminMeta"),
    adminError: document.getElementById("adminError"),
    tabUsers: document.getElementById("tabUsers"),
    tabFiles: document.getElementById("tabFiles"),
    viewUsers: document.getElementById("viewUsers"),
    viewFiles: document.getElementById("viewFiles"),
    usersMeta: document.getElementById("usersMeta"),
    usersTbody: document.getElementById("usersTbody"),
    filesMeta: document.getElementById("filesMeta"),
    filesTbody: document.getElementById("filesTbody"),
  };

  let me = null;
  let users = [];
  let docs = [];
  let activeView = "users";

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function clearError() {
    if (!els.adminError) return;
    els.adminError.style.display = "none";
    els.adminError.textContent = "";
  }

  function setError(message) {
    if (!els.adminError) return;
    els.adminError.style.display = "";
    els.adminError.textContent = message;
  }

  function setAdminMeta(text) {
    if (!els.adminMeta) return;
    els.adminMeta.textContent = text || "—";
  }

  function setUserNav() {
    if (els.userBadge) {
      els.userBadge.style.display = "";
      const who = me.email || me.username || "—";
      const role = String(me.role || "");
      const roleLabel = ["user", "moderator", "admin"].includes(role) ? role : "user";
      els.userBadge.textContent = `${who} • ${roleLabel}`;
    }
    if (els.logoutBtn) {
      els.logoutBtn.style.display = "";
      els.logoutBtn.addEventListener("click", () => Auth.logout());
    }
  }

  function normalizeStatus(status) {
    if (status === "parsed") return "Готово";
    if (status === "uploaded") return "Загружено";
    if (status === "error") return "Ошибка";
    return status || "—";
  }

  function inferTitleFromFilename(name) {
    const base = String(name || "").split(/[\\/]/).pop() || "";
    return base.replace(/\.(pdf|docx)$/i, "").trim();
  }

  function docTitleOrFallback(doc) {
    const title = String(doc?.title || "").trim();
    if (title) return title;
    return inferTitleFromFilename(doc?.filename);
  }

  function docCitation(doc) {
    if (!doc) return "";
    const author = String(doc.author || "").trim();
    const title = docTitleOrFallback(doc);
    const year = doc.publication_year != null ? String(doc.publication_year) : "";

    const parts = [];
    if (author) parts.push(author);
    if (title) parts.push(title);
    const head = parts.join(" — ");
    if (year) return head ? `${head} (${year})` : year;
    return head || String(doc.filename || `#${doc?.id ?? "?"}`);
  }

  function roleOptions(selected) {
    const roles = [
      { value: "user", label: "user" },
      { value: "moderator", label: "moderator" },
      { value: "admin", label: "admin" },
    ];
    return roles
      .map((r) => `<option value="${r.value}" ${r.value === selected ? "selected" : ""}>${r.label}</option>`)
      .join("");
  }

  function updateUsersMeta() {
    if (els.usersMeta) els.usersMeta.textContent = `${users.length} пользователей`;
  }

  function updateFilesMeta() {
    if (els.filesMeta) els.filesMeta.textContent = `${docs.length} файлов`;
  }

  function renderUsers() {
    if (!els.usersTbody) return;
    els.usersTbody.innerHTML = "";

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
          <button class="btn btn--sm" data-save="${escapeHtml(u.id)}">Сохранить</button>
        </td>
      `;
      els.usersTbody.appendChild(tr);
    }

    for (const btn of els.usersTbody.querySelectorAll("[data-save]")) {
      btn.addEventListener("click", () => onSave(btn.getAttribute("data-save")));
    }
  }

  function renderFiles() {
    if (!els.filesTbody) return;
    els.filesTbody.innerHTML = "";

    if (!docs.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4"><div class="placeholder">Файлов нет.</div></td>`;
      els.filesTbody.appendChild(tr);
      return;
    }

    for (const d of docs) {
      const statusRaw = String(d.status || "");
      const statusLabel = normalizeStatus(statusRaw);
      const badge =
        statusRaw && statusRaw !== "—"
          ? `<span class="badge badge--${escapeHtml(statusRaw)}">${escapeHtml(statusLabel)}</span>`
          : escapeHtml(statusLabel);

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${escapeHtml(d.id)}</td>
        <td>
          <div>${escapeHtml(docCitation(d))}</div>
          <div class="muted mono">${escapeHtml(d.filename || "")}</div>
        </td>
        <td class="mono">${escapeHtml(d.file_type || "—")}</td>
        <td>${badge}</td>
      `;
      els.filesTbody.appendChild(tr);
    }
  }

  async function refreshUsers() {
    users = await Auth.fetchJson("/admin/users");
    if (!Array.isArray(users)) users = [];
    updateUsersMeta();
    renderUsers();
  }

  async function refreshFiles() {
    docs = await Auth.fetchJson("/documents");
    if (!Array.isArray(docs)) docs = [];
    updateFilesMeta();
    renderFiles();
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
      Auth.toast("Роль обновлена.", "success");
      await refreshUsers();
    } catch (err) {
      Auth.toast(String(err?.message || err || "Не удалось обновить роль"), "error");
      btn.disabled = false;
      btn.textContent = "Сохранить";
    }
  }

  function setView(view) {
    activeView = view === "files" ? "files" : "users";

    if (els.tabUsers) els.tabUsers.classList.toggle("is-active", activeView === "users");
    if (els.tabFiles) els.tabFiles.classList.toggle("is-active", activeView === "files");

    if (els.viewUsers) els.viewUsers.classList.toggle("is-active", activeView === "users");
    if (els.viewFiles) els.viewFiles.classList.toggle("is-active", activeView === "files");

    if (activeView === "files") {
      refreshFiles().catch((err) => Auth.toast(String(err?.message || err || "Не удалось загрузить файлы"), "error"));
    }
  }

  async function init() {
    try {
      me = await Auth.me();
      setUserNav();

      if (String(me?.role || "") !== "admin") {
        setAdminMeta("—");
        setError("Доступ только для admin.");
        return;
      }

      clearError();
      setAdminMeta("Выберите раздел");

      if (els.tabUsers) els.tabUsers.addEventListener("click", () => setView("users"));
      if (els.tabFiles) els.tabFiles.addEventListener("click", () => setView("files"));

      await refreshUsers();
      setView(activeView);
    } catch (err) {
      setAdminMeta("—");
      setError(String(err?.message || err || "Ошибка загрузки"));
    }
  }

  init();
})();
