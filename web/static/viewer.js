(function () {
  if (!Auth.requireAuthOrRedirect()) return;

  const state = {
    me: null,
    docs: [],
    docsById: new Map(),
    selectedDocId: null,
    selectedDoc: null,
    activeTab: "text",
    wordFreqByDocId: new Map(),
    renderLimits: { paragraphs: 50, sentences: 50, words: 200 },
  };

  const els = {
    userBadge: document.getElementById("userBadge"),
    adminLink: document.getElementById("adminLink"),
    moderatorLink: document.getElementById("moderatorLink"),
    logoutBtn: document.getElementById("logoutBtn"),
    docsMeta: document.getElementById("docsMeta"),
    docFilter: document.getElementById("docFilter"),
    docsList: document.getElementById("docsList"),
    docTitle: document.getElementById("docTitle"),
    docStats: document.getElementById("docStats"),
    docBody: document.getElementById("docBody"),
    downloadBtn: document.getElementById("downloadBtn"),
  };

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizeStatus(status) {
    if (status === "parsed") return "Тайёр";
    if (status === "uploaded") return "Боргузорӣ шуд";
    if (status === "error") return "Хато";
    return status || "—";
  }

  function docDisplayName(doc) {
    return String(doc?.title || doc?.filename || `#${doc?.id ?? "?"}`);
  }

  function updateUserNav() {
    const u = state.me;
    if (!u) return;
    if (els.userBadge) {
      els.userBadge.style.display = "";
      const who = u.email || u.username || "—";
      const role = String(u.role || "");
      const roleLabel = role === "admin" ? "админ" : role === "moderator" ? "модератор" : "корбар";
      els.userBadge.textContent = `${who} • ${roleLabel}`;
    }
    if (els.logoutBtn) {
      els.logoutBtn.style.display = "";
      els.logoutBtn.addEventListener("click", () => Auth.logout());
    }
    if (els.adminLink) els.adminLink.style.display = u.role === "admin" ? "" : "none";
    if (els.moderatorLink) {
      els.moderatorLink.style.display = u.role === "moderator" || u.role === "admin" ? "" : "none";
    }
  }

  function updateDocsMeta() {
    if (els.docsMeta) els.docsMeta.textContent = `${state.docs.length} файл`;
  }

  function renderDocs() {
    const filter = (els.docFilter?.value || "").trim().toLowerCase();
    const docs = filter
      ? state.docs.filter((d) => docDisplayName(d).toLowerCase().includes(filter))
      : state.docs;

    els.docsList.innerHTML = "";
    if (!docs.length) {
      const empty = document.createElement("div");
      empty.className = "placeholder";
      empty.textContent = filter ? "Ёфт нашуд." : "Ҳоло файлҳо нестанд.";
      els.docsList.appendChild(empty);
      return;
    }

    for (const doc of docs) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "docitem";
      if (doc.id === state.selectedDocId) item.classList.add("is-active");
      item.innerHTML = `
        <div class="docitem__top">
          <div class="docitem__name">${escapeHtml(docDisplayName(doc))}</div>
          <div class="badge badge--${escapeHtml(doc.status)}">${escapeHtml(normalizeStatus(doc.status))}</div>
        </div>
        <div class="docitem__meta">#${doc.id} • ${escapeHtml(doc.file_type || "—")}</div>
      `;
      item.addEventListener("click", () => selectDoc(doc.id));
      els.docsList.appendChild(item);
    }
  }

  async function refreshDocs({ keepSelection = true } = {}) {
    const docs = await Auth.fetchJson("/documents");
    state.docs = Array.isArray(docs) ? docs : [];
    state.docsById = new Map(state.docs.map((d) => [d.id, d]));
    updateDocsMeta();

    if (!keepSelection) {
      state.selectedDocId = null;
      state.selectedDoc = null;
    } else if (!state.selectedDocId || !state.docsById.has(state.selectedDocId)) {
      state.selectedDocId = null;
      state.selectedDoc = null;
    }

    renderDocs();
    renderSelectedDoc();
  }

  function renderStats(doc) {
    if (!doc) {
      els.docStats.innerHTML = "";
      return;
    }

    const paragraphsCount = Array.isArray(doc.paragraphs) ? doc.paragraphs.length : 0;
    const sentencesCount = Array.isArray(doc.sentences) ? doc.sentences.length : 0;
    const wordsCount = Array.isArray(doc.words) ? doc.words.length : 0;

    const status = normalizeStatus(doc.status);
    const error = doc.error_message ? `<span class="stats__error">${escapeHtml(doc.error_message)}</span>` : "";

    const author = doc.author
      ? `<div class="stat"><div class="stat__k">Муаллиф</div><div class="stat__v">${escapeHtml(doc.author)}</div></div>`
      : "";
    const publisher = doc.publisher
      ? `<div class="stat"><div class="stat__k">Нашркунанда</div><div class="stat__v">${escapeHtml(doc.publisher)}</div></div>`
      : "";
    const year =
      doc.publication_year != null
        ? `<div class="stat"><div class="stat__k">Сол</div><div class="stat__v">${escapeHtml(doc.publication_year)}</div></div>`
        : "";

    els.docStats.innerHTML = `
      <div class="stat"><div class="stat__k">Ҳолат</div><div class="stat__v">${escapeHtml(status)}</div></div>
      <div class="stat"><div class="stat__k">Бандҳо</div><div class="stat__v">${paragraphsCount}</div></div>
      <div class="stat"><div class="stat__k">Ҷумлаҳо</div><div class="stat__v">${sentencesCount}</div></div>
      <div class="stat"><div class="stat__k">Калимаҳо</div><div class="stat__v">${wordsCount}</div></div>
      ${author}
      ${publisher}
      ${year}
      ${
        doc.bibliography
          ? `<div class="stat stat--wide"><div class="stat__k">Библиография</div><div class="stat__v">${escapeHtml(doc.bibliography)}</div></div>`
          : ""
      }
      ${error ? `<div class="stat stat--wide">${error}</div>` : ""}
    `;
  }

  function renderDocText(doc) {
    const text = doc?.full_text || "";
    if (!text) return `<div class="placeholder">Матн холӣ аст.</div>`;
    return `<pre class="pre">${escapeHtml(text)}</pre>`;
  }

  function renderIndexList(items, { label, limit, renderItem }) {
    const total = items.length;
    const shown = Math.min(total, limit);
    if (!total) return `<div class="placeholder">Маълумот нест.</div>`;

    const list = items.slice(0, shown).map(renderItem).join("");
    const more =
      total > shown
        ? `<button class="btn btn--ghost" type="button" data-more="${label}">Бештар (${total - shown})</button>`
        : "";
    return `<div class="vlist">${list}${more}</div>`;
  }

  function renderParagraphs(doc) {
    const paragraphs = Array.isArray(doc?.paragraphs) ? doc.paragraphs : [];
    return renderIndexList(paragraphs, {
      label: "paragraphs",
      limit: state.renderLimits.paragraphs,
      renderItem: (p) => `
        <div class="vitem">
          <div class="vitem__meta">Банд ${p.paragraph_index}</div>
          <div class="vitem__text">${escapeHtml(p.text)}</div>
        </div>
      `,
    });
  }

  function renderSentences(doc) {
    const sentences = Array.isArray(doc?.sentences) ? doc.sentences : [];
    return renderIndexList(sentences, {
      label: "sentences",
      limit: state.renderLimits.sentences,
      renderItem: (s) => `
        <div class="vitem">
          <div class="vitem__meta">Банд ${s.paragraph_index ?? "—"} • Ҷумла ${s.sentence_index}</div>
          <div class="vitem__text">${escapeHtml(s.text)}</div>
        </div>
      `,
    });
  }

  function getDocWordFrequency(doc) {
    const docId = doc?.id;
    const words = Array.isArray(doc?.words) ? doc.words : [];
    if (!docId || !words.length) return { freq: new Map(), unique: 0, total: words.length };

    const cached = state.wordFreqByDocId.get(docId);
    if (cached && cached.total === words.length) return cached;

    const freq = new Map();
    for (const item of words) {
      const word = String(item?.word || "").trim();
      if (!word) continue;
      const key = word.toLowerCase();
      freq.set(key, (freq.get(key) || 0) + 1);
    }
    const computed = { freq, unique: freq.size, total: words.length };
    state.wordFreqByDocId.set(docId, computed);
    return computed;
  }

  function renderWords(doc) {
    const words = Array.isArray(doc?.words) ? doc.words : [];
    const { freq, unique, total } = getDocWordFrequency(doc);
    const metaTj = total ? `<div class="muted">Ҳамагӣ: ${total} • Беназир: ${unique}</div>` : "";

    return (
      metaTj +
      renderIndexList(words, {
        label: "words",
        limit: state.renderLimits.words,
        renderItem: (w) => {
          const word = String(w?.word || "");
          const count = freq.get(word.toLowerCase()) || 0;
          return `
            <div class="vitem">
              <div class="vitem__meta">Ҷумла ${w.sentence_index ?? "—"} • #${w.word_index}</div>
              <div class="vitem__text row row--between">
                <span class="mono">${escapeHtml(word)}</span>
                <span class="badge badge--count">×${escapeHtml(count)}</span>
              </div>
            </div>
          `;
        },
      })
    );
  }

  function renderSelectedDoc() {
    const doc = state.selectedDoc;
    if (!doc) {
      if (els.docTitle) els.docTitle.textContent = "—";
      els.docBody.innerHTML = `<div class="placeholder">Файлро аз рӯйхати чап интихоб кунед.</div>`;
      renderStats(null);
      els.downloadBtn.disabled = true;
      return;
    }

    if (els.docTitle) els.docTitle.textContent = docDisplayName(doc);
    renderStats(doc);

    let html = "";
    if (state.activeTab === "text") html = renderDocText(doc);
    if (state.activeTab === "paragraphs") html = renderParagraphs(doc);
    if (state.activeTab === "sentences") html = renderSentences(doc);
    if (state.activeTab === "words") html = renderWords(doc);

    els.docBody.innerHTML = html;
    els.downloadBtn.disabled = false;

    const more = els.docBody.querySelector("[data-more]");
    if (more) {
      more.addEventListener("click", () => {
        const key = more.getAttribute("data-more");
        state.renderLimits[key] = (state.renderLimits[key] || 0) + 100;
        renderSelectedDoc();
      });
    }
  }

  async function selectDoc(docId) {
    state.selectedDocId = docId;
    renderDocs();
    els.docBody.innerHTML = `<div class="placeholder">Файл бор мешавад…</div>`;
    els.downloadBtn.disabled = true;

    try {
      const doc = await Auth.fetchJson(`/documents/${docId}`);
      state.selectedDoc = doc;
      renderSelectedDoc();
    } catch (err) {
      state.selectedDoc = null;
      renderSelectedDoc();
      Auth.toast(String(err?.message || err || "Файл бор карда нашуд"), "error");
    }
  }

  function setTab(tab) {
    state.activeTab = tab;
    for (const btn of document.querySelectorAll("[data-tab]")) {
      btn.classList.toggle("is-active", btn.dataset.tab === tab);
    }
    renderSelectedDoc();
  }

  async function onDownload() {
    const doc = state.selectedDoc;
    if (!doc?.id) return;

    try {
      const blob = await Auth.fetchBlob(`/documents/${doc.id}/file`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = doc.filename || "";
      link.rel = "noreferrer";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      Auth.toast(String(err?.message || err || "Зеркашӣ иҷро нашуд"), "error");
    }
  }

  function attachEvents() {
    if (els.docFilter) els.docFilter.addEventListener("input", renderDocs);
    if (els.downloadBtn) els.downloadBtn.addEventListener("click", onDownload);
    for (const btn of document.querySelectorAll("[data-tab]")) {
      btn.addEventListener("click", () => setTab(btn.dataset.tab));
    }
  }

  async function init() {
    try {
      state.me = await Auth.me();
      updateUserNav();

      attachEvents();
      await refreshDocs();
    } catch (err) {
      Auth.toast(String(err?.message || err || "Хато"), "error");
    }
  }

  init();
})();
