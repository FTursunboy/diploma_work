/* eslint-disable no-alert */
const state = {
  me: null,
  docs: [],
  docsById: new Map(),
  selectedDocId: null,
  selectedDoc: null,
  activeView: "search",
  activeTab: "text",
  focus: null, // { documentId, paragraphIndex, sentenceIndex, query }
  wordFreqByDocId: new Map(),
  renderLimits: {
    paragraphs: 50,
    sentences: 50,
    words: 200,
  },
};

const els = {
  userBadge: document.getElementById("userBadge"),
  adminLink: document.getElementById("adminLink"),
  loginLink: document.getElementById("loginLink"),
  registerLink: document.getElementById("registerLink"),
  logoutBtn: document.getElementById("logoutBtn"),
  docsMeta: document.getElementById("docsMeta"),
  docFilter: document.getElementById("docFilter"),
  docsList: document.getElementById("docsList"),
  uploadCard: document.getElementById("uploadCard"),
  openUploadModalBtn: document.getElementById("openUploadModalBtn"),
  uploadModal: document.getElementById("uploadModal"),
  uploadModalForm: document.getElementById("uploadModalForm"),
  uploadFile: document.getElementById("uploadFile"),
  uploadBtn: document.getElementById("uploadBtn"),
  metaTitle: document.getElementById("metaTitle"),
  metaAuthor: document.getElementById("metaAuthor"),
  metaYear: document.getElementById("metaYear"),
  metaPublisher: document.getElementById("metaPublisher"),
  metaBib: document.getElementById("metaBib"),
  searchForm: document.getElementById("searchForm"),
  searchQuery: document.getElementById("searchQuery"),
  searchTarget: document.getElementById("searchTarget"),
  searchDocument: document.getElementById("searchDocument"),
  searchWordMode: document.getElementById("searchWordMode"),
  wordModeWrap: document.getElementById("wordModeWrap"),
  searchBtn: document.getElementById("searchBtn"),
  viewSearch: document.getElementById("viewSearch"),
  viewConcordance: document.getElementById("viewConcordance"),
  viewWordlist: document.getElementById("viewWordlist"),
  viewNgrams: document.getElementById("viewNgrams"),
  concordanceForm: document.getElementById("concordanceForm"),
  concordanceQuery: document.getElementById("concordanceQuery"),
  concordanceMode: document.getElementById("concordanceMode"),
  concordanceDocument: document.getElementById("concordanceDocument"),
  concordanceBtn: document.getElementById("concordanceBtn"),
  wordlistForm: document.getElementById("wordlistForm"),
  wordlistFilter: document.getElementById("wordlistFilter"),
  wordlistMode: document.getElementById("wordlistMode"),
  wordlistDocument: document.getElementById("wordlistDocument"),
  wordlistMinFreq: document.getElementById("wordlistMinFreq"),
  wordlistBtn: document.getElementById("wordlistBtn"),
  ngramsForm: document.getElementById("ngramsForm"),
  ngramsQuery: document.getElementById("ngramsQuery"),
  ngramsN: document.getElementById("ngramsN"),
  ngramsDocument: document.getElementById("ngramsDocument"),
  ngramsMinFreq: document.getElementById("ngramsMinFreq"),
  ngramsBtn: document.getElementById("ngramsBtn"),
  resultsMeta: document.getElementById("resultsMeta"),
  resultsList: document.getElementById("resultsList"),
  docTitle: document.getElementById("docTitle"),
  docStats: document.getElementById("docStats"),
  docBody: document.getElementById("docBody"),
  downloadBtn: document.getElementById("downloadBtn"),
  deleteBtn: document.getElementById("deleteBtn"),
  toast: document.getElementById("toast"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message, type = "info") {
  if (window.Auth?.toast) return window.Auth.toast(message, type);
  // fallback
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.dataset.type = type;
  els.toast.classList.add("is-visible");
  window.clearTimeout(toast._t);
  toast._t = window.setTimeout(() => els.toast.classList.remove("is-visible"), 3200);
}

async function fetchJson(path, options) {
  if (window.Auth?.fetchJson) return window.Auth.fetchJson(path, options);
  const res = await fetch(path, options);
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || res.statusText || "Хатои дархост");
  return res.json();
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = !!busy;
  if (label) button.textContent = label;
}

function setAuthNav(user) {
  if (!user) return;
  const who = user.email || user.username || "—";
  const role = String(user.role || "");
  const roleLabel = ["user", "moderator", "admin"].includes(role) ? role : "user";
  if (els.userBadge) {
    els.userBadge.style.display = "";
    els.userBadge.textContent = `${who} • ${roleLabel}`;
  }
  if (els.adminLink) els.adminLink.style.display = role === "admin" ? "" : "none";
  if (els.loginLink) els.loginLink.style.display = "none";
  if (els.registerLink) els.registerLink.style.display = "none";
  if (els.logoutBtn) {
    els.logoutBtn.style.display = "";
    els.logoutBtn.addEventListener("click", () => window.Auth?.logout?.());
  }

  const canModerate = role === "moderator" || role === "admin";
  if (els.uploadCard) els.uploadCard.style.display = canModerate ? "" : "none";
  if (els.deleteBtn) els.deleteBtn.style.display = role === "admin" ? "" : "none";
}

function normalizeStatus(status) {
  if (status === "parsed") return "Тайёр";
  if (status === "uploaded") return "Боргузорӣ шуд";
  if (status === "error") return "Хато";
  return status || "—";
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
  return head || String(doc.filename || `Файл #${doc?.id ?? "?"}`);
}

function docFilterText(doc) {
  const bits = [
    docCitation(doc),
    doc?.bibliography,
    doc?.publisher,
    doc?.doc_type,
    doc?.filename,
    doc?.file_type,
    doc?.id != null ? `#${doc.id}` : "",
  ]
    .map((v) => String(v || "").trim())
    .filter(Boolean);
  return bits.join(" ").toLowerCase();
}

function updateDocsMeta() {
  els.docsMeta.textContent = `${state.docs.length} файл`;
}

function renderDocs() {
  const filter = (els.docFilter.value || "").trim().toLowerCase();
  const docs = filter
    ? state.docs.filter((d) => docFilterText(d).includes(filter))
    : state.docs;

  els.docsList.innerHTML = "";
  if (!docs.length) {
    const empty = document.createElement("div");
    empty.className = "placeholder";
    empty.textContent = filter ? "Ёфт нашуд." : "Ҳоло файлҳо нестанд. Файл боргузорӣ кунед.";
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
        <div class="docitem__name">${escapeHtml(docCitation(doc))}</div>
        <div class="badge badge--${escapeHtml(doc.status)}">${escapeHtml(normalizeStatus(doc.status))}</div>
      </div>
      <div class="docitem__meta">#${doc.id} • ${escapeHtml(doc.file_type || "—")}</div>
    `;
    item.addEventListener("click", () => selectDoc(doc.id, { focus: null }));
    els.docsList.appendChild(item);
  }
}

function renderDocSelect(selectEl) {
  if (!selectEl) return;
  const current = selectEl.value;
  const options = [
    { value: "", label: "Ҳамаи файлҳо" },
    ...state.docs.map((d) => ({ value: String(d.id), label: `#${d.id} — ${docCitation(d)}` })),
  ];

  selectEl.innerHTML = "";
  for (const opt of options) {
    const option = document.createElement("option");
    option.value = opt.value;
    option.textContent = opt.label;
    selectEl.appendChild(option);
  }

  if ([...selectEl.options].some((o) => o.value === current)) {
    selectEl.value = current;
  }
}

async function refreshDocs({ keepSelection = true } = {}) {
  try {
    const docs = await fetchJson("/documents");
    state.docs = Array.isArray(docs) ? docs : [];
    state.docsById = new Map(state.docs.map((d) => [d.id, d]));
    updateDocsMeta();
    renderDocSelect(els.searchDocument);
    renderDocSelect(els.concordanceDocument);
    renderDocSelect(els.wordlistDocument);
    renderDocSelect(els.ngramsDocument);

    if (!keepSelection) {
      state.selectedDocId = null;
      state.selectedDoc = null;
    } else if (state.selectedDocId && state.docsById.has(state.selectedDocId)) {
      // keep
    } else {
      state.selectedDocId = null;
      state.selectedDoc = null;
    }

    renderDocs();
    renderSelectedDoc();
  } catch (err) {
    toast(`Рӯйхати файлҳоро бор карда нашуд: ${String(err.message || err)}`, "error");
  }
}

async function uploadDocument(file) {
  return fetchJson("/documents/upload", { method: "POST", body: file });
}

function setModalOpen(open) {
  if (!els.uploadModal) return;
  els.uploadModal.classList.toggle("is-open", !!open);
  els.uploadModal.setAttribute("aria-hidden", open ? "false" : "true");
  document.documentElement.style.overflow = open ? "hidden" : "";
  if (open) {
    window.setTimeout(() => els.metaTitle?.focus?.(), 0);
  }
}

function inferTitleFromFilename(name) {
  const base = String(name || "").split(/[\\/]/).pop() || "";
  return base.replace(/\.(pdf|docx)$/i, "").trim();
}

function buildBibliography({ author, title, publisher, year }) {
  const a = String(author || "").trim();
  const t = String(title || "").trim();
  const p = String(publisher || "").trim();
  const y = String(year || "").trim();
  const parts = [];
  if (a) parts.push(a);
  if (t) parts.push(t);
  const tail = [p, y].filter(Boolean).join(", ");
  if (tail) parts.push(`— ${tail}.`);
  return parts.join(". ");
}

async function onUploadModalSubmit(e) {
  e.preventDefault();
  const file = els.uploadFile?.files?.[0];
  if (!file) return toast("Файли PDF/DOCX-ро интихоб кунед.", "warning");

  const title = String(els.metaTitle?.value || "").trim();
  const author = String(els.metaAuthor?.value || "").trim();
  const publisher = String(els.metaPublisher?.value || "").trim();
  const year = String(els.metaYear?.value || "").trim();
  const bibliography = String(els.metaBib?.value || "").trim();

  if (!title || !author || !publisher || !year || !bibliography) {
    return toast("Лутфан ҳамаи майдонҳоро пур кунед.", "warning");
  }

  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("author", author);
  form.append("publisher", publisher);
  form.append("publication_year", year);
  form.append("bibliography", bibliography);

  setBusy(els.uploadBtn, true, "Боргузорӣ…");
  try {
    const doc = await uploadDocument(form);
    toast("Файл боргузорӣ ва коркард шуд.", "success");
    await refreshDocs({ keepSelection: true });
    if (doc?.id) await selectDoc(doc.id);
    if (els.uploadModalForm) els.uploadModalForm.reset();
    setModalOpen(false);
  } catch (err) {
    toast(`Хатои боргузорӣ: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.uploadBtn, false, "Боргузорӣ");
  }
}

function setTab(tab) {
  state.activeTab = tab;
  for (const btn of document.querySelectorAll("[data-tab]")) {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  }
  renderSelectedDoc();
}

function setView(view) {
  state.activeView = view;
  for (const btn of document.querySelectorAll("[data-view]")) {
    btn.classList.toggle("is-active", btn.dataset.view === view);
  }

  if (els.viewSearch) els.viewSearch.classList.toggle("is-active", view === "search");
  if (els.viewConcordance) els.viewConcordance.classList.toggle("is-active", view === "concordance");
  if (els.viewWordlist) els.viewWordlist.classList.toggle("is-active", view === "wordlist");
  if (els.viewNgrams) els.viewNgrams.classList.toggle("is-active", view === "ngrams");

  if (view === "ngrams" && els.ngramsBtn) {
    const query = String(els.ngramsQuery?.value || "").trim();
    els.ngramsBtn.textContent = query ? "Ёфтан" : "Сохтан";
  }
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

  const author = doc.author ? `<div class="stat"><div class="stat__k">Муаллиф</div><div class="stat__v">${escapeHtml(doc.author)}</div></div>` : "";
  const publisher = doc.publisher
    ? `<div class="stat"><div class="stat__k">Ношир</div><div class="stat__v">${escapeHtml(doc.publisher)}</div></div>`
    : "";
  const year =
    doc.publication_year != null
      ? `<div class="stat"><div class="stat__k">Сол</div><div class="stat__v">${escapeHtml(doc.publication_year)}</div></div>`
      : "";

  els.docStats.innerHTML = `
    <div class="stat"><div class="stat__k">Ҳолат</div><div class="stat__v">${escapeHtml(status)}</div></div>
    <div class="stat"><div class="stat__k">Абзатсҳо</div><div class="stat__v">${paragraphsCount}</div></div>
    <div class="stat"><div class="stat__k">Ҷумлаҳо</div><div class="stat__v">${sentencesCount}</div></div>
    <div class="stat"><div class="stat__k">Калимаҳо</div><div class="stat__v">${wordsCount}</div></div>
    ${author}
    ${publisher}
    ${year}
    ${doc.bibliography ? `<div class="stat stat--wide"><div class="stat__k">Библиография</div><div class="stat__v">${escapeHtml(doc.bibliography)}</div></div>` : ""}
    ${error ? `<div class="stat stat--wide">${error}</div>` : ""}
  `;
}

function renderDocText(doc) {
  const focus = state.focus;
  if (focus && Number(focus.documentId) === Number(doc?.id) && focus.paragraphIndex != null) {
    const paragraphs = Array.isArray(doc?.paragraphs) ? doc.paragraphs : [];
    const indices = paragraphs
      .map((x) => Number(x?.paragraph_index))
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b);
    const p = paragraphs.find((x) => Number(x?.paragraph_index) === Number(focus.paragraphIndex));
    const text = String(p?.text || "").trim();
    if (text) {
      const pos = indices.length ? indices.indexOf(Number(focus.paragraphIndex)) + 1 : 0;
      const counter = pos > 0 ? ` (${pos}/${indices.length})` : "";
      const prev = pos > 1 ? indices[pos - 2] : null;
      const next = pos > 0 && pos < indices.length ? indices[pos] : null;

      return `
        <div class="focusbar">
          <div class="focusbar__meta">Абзац ${escapeHtml(focus.paragraphIndex)}${escapeHtml(counter)}</div>
          <div class="row">
            <button class="btn btn--sm" type="button" data-focus="prev" ${prev == null ? "disabled" : ""}>←</button>
            <button class="btn btn--sm" type="button" data-focus="next" ${next == null ? "disabled" : ""}>→</button>
          </div>
        </div>
        <pre class="pre">${highlight(text, focus.query || "")}</pre>
      `;
    }
  }

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
        <div class="vitem__meta">Абзатс ${p.paragraph_index}</div>
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
        <div class="vitem__meta">Абзатс ${s.paragraph_index ?? "—"} • Ҷумла ${s.sentence_index}</div>
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
  const meta = total
    ? `<div class="muted">Ҳамагӣ: ${total} • Беназир: ${unique}</div>`
    : "";

  return (
    meta +
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
              <span class="badge badge--count">×${count}</span>
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
    els.docTitle.textContent = "—";
    els.docBody.innerHTML = `<div class="placeholder">Файлро аз рӯйхати чап интихоб кунед.</div>`;
    renderStats(null);
    els.downloadBtn.disabled = true;
    els.deleteBtn.disabled = true;
    return;
  }

  els.docTitle.textContent = docCitation(doc);
  renderStats(doc);

  let html = "";
  if (state.activeTab === "text") html = renderDocText(doc);
  if (state.activeTab === "paragraphs") html = renderParagraphs(doc);
  if (state.activeTab === "sentences") html = renderSentences(doc);
  if (state.activeTab === "words") html = renderWords(doc);

  els.docBody.innerHTML = html;
  els.downloadBtn.disabled = false;
  els.deleteBtn.disabled = !(state.me && state.me.role === "admin");

  const more = els.docBody.querySelector("[data-more]");
  if (more) {
    more.addEventListener("click", () => {
      const key = more.getAttribute("data-more");
      state.renderLimits[key] = (state.renderLimits[key] || 0) + 100;
      renderSelectedDoc();
    });
  }
}

async function selectDoc(docId, { focus } = {}) {
  if (focus === undefined) {
    state.focus = null;
  } else {
    state.focus = focus;
    if (state.focus && state.activeTab !== "text") setTab("text");
  }

  state.selectedDocId = docId;
  renderDocs();

  els.docBody.innerHTML = `<div class="placeholder">Файл бор мешавад…</div>`;
  els.downloadBtn.disabled = true;
  els.deleteBtn.disabled = true;

  try {
    const doc = await fetchJson(`/documents/${docId}`);
    state.selectedDoc = doc;
    renderSelectedDoc();
  } catch (err) {
    state.selectedDoc = null;
    renderSelectedDoc();
    toast(`Файл бор карда нашуд: ${String(err.message || err)}`, "error");
  }
}

function setFocusForSelectedDoc(nextFocus) {
  state.focus = nextFocus || null;
  if (state.focus && state.activeTab !== "text") {
    setTab("text");
    return;
  }
  renderSelectedDoc();
}

function onDocBodyClick(e) {
  const btn = e.target?.closest?.("[data-focus]");
  if (!btn) return;
  const action = btn.getAttribute("data-focus");
  const doc = state.selectedDoc;
  const focus = state.focus;
  if (!doc || !focus || focus.paragraphIndex == null) return;

  const paragraphs = Array.isArray(doc?.paragraphs) ? doc.paragraphs : [];
  const indices = paragraphs
    .map((x) => Number(x?.paragraph_index))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b);
  const pos = indices.indexOf(Number(focus.paragraphIndex));
  if (pos < 0) return;

  let nextIndex = null;
  if (action === "prev" && pos > 0) nextIndex = indices[pos - 1];
  if (action === "next" && pos + 1 < indices.length) nextIndex = indices[pos + 1];
  if (nextIndex == null) return;

  setFocusForSelectedDoc({
    documentId: focus.documentId,
    paragraphIndex: nextIndex,
    sentenceIndex: null,
    query: focus.query,
  });
}

function setWordModeVisibility() {
  const isWord = els.searchTarget.value === "word";
  if (!els.wordModeWrap || !els.searchWordMode) return;
  els.wordModeWrap.style.display = isWord ? "" : "none";
  els.searchWordMode.disabled = !isWord;
  if (!isWord) els.searchWordMode.value = "partial";
}

function highlight(text, query) {
  const q = (query || "").trim();
  if (!q) return escapeHtml(text);

  const source = String(text || "");
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  let out = "";
  let last = 0;

  let m;
  while ((m = re.exec(source)) !== null) {
    out += escapeHtml(source.slice(last, m.index));
    out += `<mark>${escapeHtml(m[0])}</mark>`;
    last = m.index + m[0].length;
    if (m[0].length === 0) re.lastIndex += 1;
  }

  out += escapeHtml(source.slice(last));
  return out;
}

function renderResults(data, query) {
  const total = data?.total ?? 0;
  const results = Array.isArray(data?.results) ? data.results : [];
  const target = String(data?.target || "");
  const docIds = new Set(results.map((r) => r?.document_id).filter(Boolean));
  const docsHint = docIds.size > 1 ? ` • файлҳо: ${docIds.size}` : "";

  if (target === "word") {
    els.resultsMeta.textContent = `«${query}» — ${total} маротиба${docsHint}`;
  } else {
    els.resultsMeta.textContent = `Ёфт шуд: ${total}${docsHint}`;
  }
  els.resultsList.innerHTML = "";

  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "placeholder";
    empty.textContent = "Мутобиқат нест.";
    els.resultsList.appendChild(empty);
    return;
  }

  for (const r of results) {
    const doc = state.docsById.get(r.document_id);
    const docName = docCitation(doc) || `Файл #${r.document_id}`;
    const p = r.paragraph_index != null ? `Абзатс ${r.paragraph_index}` : null;
    const s = r.sentence_index != null ? `Ҷумла ${r.sentence_index}` : null;
    const where = [p, s].filter(Boolean).join(" • ") || "—";

    const card = document.createElement("button");
    card.type = "button";
    card.className = "result";
    card.innerHTML = `
      <div class="result__top">
        <div class="result__doc">${escapeHtml(docName)}</div>
        <div class="result__where">${escapeHtml(where)}</div>
      </div>
      <div class="result__text">${highlight(String(r.text || ""), query)}</div>
    `;
    card.addEventListener("click", () =>
      selectDoc(r.document_id, {
        focus: {
          documentId: r.document_id,
          paragraphIndex: r.paragraph_index,
          sentenceIndex: r.sentence_index,
          query,
        },
      })
    );
    els.resultsList.appendChild(card);
  }
}

async function performSearch({ query, target, documentId, mode } = {}) {
  const q = (query || "").trim();
  if (!q) return;
  const t = target || "phrase";

  const params = new URLSearchParams({ query: q, target: t });
  if (t === "word" && mode) params.set("mode", mode);
  if (documentId) params.set("document_id", String(documentId));

  const data = await fetchJson(`/search?${params.toString()}`);
  renderResults(data, q);
}

async function onSearch(e) {
  e.preventDefault();

  setBusy(els.searchBtn, true, "Ҷустуҷӯ…");
  try {
    const query = (els.searchQuery.value || "").trim();
    const target = els.searchTarget.value || "phrase";
    const docId = els.searchDocument.value;
    const mode = target === "word" ? els.searchWordMode.value : null;
    await performSearch({ query, target, documentId: docId || null, mode });
  } catch (err) {
    toast(`Хатои ҷустуҷӯ: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.searchBtn, false, "Ҷустуҷӯ");
  }
}

function renderToolEmpty(message = "Маълумот нест.") {
  els.resultsList.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "placeholder";
  empty.textContent = message;
  els.resultsList.appendChild(empty);
}

function renderConcordance(data) {
  const total = data?.total ?? 0;
  const items = Array.isArray(data?.items) ? data.items : [];
  els.resultsMeta.textContent = `Concordance: ${total}`;
  els.resultsList.innerHTML = "";

  if (!items.length) return renderToolEmpty("Мутобиқат нест.");

  for (const it of items) {
    const doc = state.docsById.get(it?.document_id);
    const docName = docCitation(doc) || it?.filename || `Файл #${it?.document_id ?? "?"}`;
    const p = it?.paragraph_index != null ? `Абзатс ${it.paragraph_index}` : null;
    const s = it?.sentence_index != null ? `Ҷумла ${it.sentence_index}` : null;
    const where = [p, s].filter(Boolean).join(" • ") || "—";

    const card = document.createElement("button");
    card.type = "button";
    card.className = "result";
    card.innerHTML = `
      <div class="result__top">
        <div class="result__doc">${escapeHtml(docName)}</div>
        <div class="result__where">${escapeHtml(where)}</div>
      </div>
      <div class="result__text result__text--full">
        <div class="kwic">
          <span class="kwic__left">${escapeHtml(it.left || "")}</span>
          <span class="kwic__match">${escapeHtml(it.match || "")}</span>
          <span class="kwic__right">${escapeHtml(it.right || "")}</span>
        </div>
      </div>
    `;
    card.addEventListener("click", () =>
      selectDoc(it.document_id, {
        focus: {
          documentId: it.document_id,
          paragraphIndex: it.paragraph_index,
          sentenceIndex: it.sentence_index,
          query: String(els.concordanceQuery?.value || "").trim(),
        },
      })
    );
    els.resultsList.appendChild(card);
  }
}

async function onConcordance(e) {
  e.preventDefault();
  const query = (els.concordanceQuery.value || "").trim();
  if (!query) return;

  const docId = els.concordanceDocument.value;
  const mode = els.concordanceMode.value || "partial";
  const params = new URLSearchParams({ query, mode, window: "5", limit: "200" });
  if (docId) params.set("document_id", docId);

  setBusy(els.concordanceBtn, true, "…");
  try {
    const data = await fetchJson(`/tools/concordance?${params.toString()}`);
    renderConcordance(data);
  } catch (err) {
    toast(`Хатои concordance: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.concordanceBtn, false, "Показать");
  }
}

function renderWordlist(data, filterText) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const filter = String(filterText || "").trim().toLowerCase();
  const mode = String(els.wordlistMode?.value || "partial");
  const shown = items.filter((it) => {
    if (!filter) return true;
    const w = String(it.word || "").toLowerCase();
    if (mode === "exact") return w === filter;
    return w.includes(filter);
  });

  els.resultsMeta.textContent = `Wordlist: ${shown.length}`;
  els.resultsList.innerHTML = "";
  if (!shown.length) return renderToolEmpty("Мутобиқат нест.");

  const sourceDocId = els.wordlistDocument.value || "";
  for (const it of shown) {
    const word = String(it.word || "");
    const count = it.count ?? 0;

    const card = document.createElement("button");
    card.type = "button";
    card.className = "result";
    card.innerHTML = `
      <div class="result__top">
        <div class="result__doc"><span class="mono">${escapeHtml(word)}</span></div>
        <div class="badge badge--count">×${escapeHtml(count)}</div>
      </div>
      <div class="result__text">Клик кунед, то ҷустуҷӯи дақиқ иҷро шавад.</div>
    `;
    card.addEventListener("click", async () => {
      els.searchQuery.value = word;
      els.searchTarget.value = "word";
      setWordModeVisibility();
      const mode = String(els.wordlistMode?.value || "exact");
      els.searchWordMode.value = mode === "partial" ? "partial" : "exact";
      els.searchDocument.value = sourceDocId;
      setView("search");
      try {
        await performSearch({
          query: word,
          target: "word",
          documentId: sourceDocId || null,
          mode: els.searchWordMode.value,
        });
      } catch (err) {
        toast(`Хатои ҷустуҷӯ: ${String(err.message || err)}`, "error");
      }
    });
    els.resultsList.appendChild(card);
  }
}

async function onWordlist(e) {
  e.preventDefault();
  const docId = els.wordlistDocument.value;
  const minFreq = Number(els.wordlistMinFreq.value || 2);
  const params = new URLSearchParams({ min_freq: String(minFreq), limit: "500" });
  if (docId) params.set("document_id", docId);

  setBusy(els.wordlistBtn, true, "…");
  try {
    const data = await fetchJson(`/tools/wordlist?${params.toString()}`);
    renderWordlist(data, els.wordlistFilter.value);
  } catch (err) {
    toast(`Хатои wordlist: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.wordlistBtn, false, "Сохтан");
  }
}

function renderNgrams(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  els.resultsMeta.textContent = `N-grams: ${items.length}`;
  els.resultsList.innerHTML = "";
  if (!items.length) return renderToolEmpty("Маълумот нест.");

  const sourceDocId = els.ngramsDocument.value || "";
  for (const it of items) {
    const ngram = String(it.ngram || "");
    const count = it.count ?? 0;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result";
    card.innerHTML = `
      <div class="result__top">
        <div class="result__doc"><span class="mono">${escapeHtml(ngram)}</span></div>
        <div class="badge badge--count">×${escapeHtml(count)}</div>
      </div>
      <div class="result__text">Клик кунед, то ҷустуҷӯ аз рӯи «Ибора» иҷро шавад.</div>
    `;
    card.addEventListener("click", async () => {
      els.searchQuery.value = ngram;
      els.searchTarget.value = "phrase";
      setWordModeVisibility();
      els.searchDocument.value = sourceDocId;
      setView("search");
      try {
        await performSearch({ query: ngram, target: "phrase", documentId: sourceDocId || null });
      } catch (err) {
        toast(`Хатои ҷустуҷӯ: ${String(err.message || err)}`, "error");
      }
    });
    els.resultsList.appendChild(card);
  }
}

function renderNgramSearch(data) {
  const query = String(data?.query || "").trim();
  const total = data?.total ?? 0;
  const items = Array.isArray(data?.items) ? data.items : [];
  const suffix = data?.document_id ? " (дар файли интихобшуда)" : "";

  els.resultsMeta.textContent = `Ҷустуҷӯи ибора: «${query}» — ${total}${suffix}`;
  els.resultsList.innerHTML = "";

  if (!items.length) return renderToolEmpty("Мутобиқат нест.");

  for (const it of items) {
    const doc = state.docsById.get(it?.document_id);
    const docName = docCitation(doc) || it?.title || it?.filename || `Файл #${it?.document_id ?? "?"}`;
    const count = it?.count ?? 0;

    const card = document.createElement("button");
    card.type = "button";
    card.className = "result";
    card.innerHTML = `
      <div class="result__top">
        <div class="result__doc">${escapeHtml(docName)}</div>
        <div class="badge badge--count">×${escapeHtml(count)}</div>
      </div>
      <div class="result__text">Клик кунед, то файл кушода шавад.</div>
    `;
    card.addEventListener("click", () => selectDoc(it.document_id, { focus: null }));
    els.resultsList.appendChild(card);
  }
}

async function onNgrams(e) {
  e.preventDefault();
  const docId = els.ngramsDocument.value;
  const query = String(els.ngramsQuery?.value || "").trim();

  setBusy(els.ngramsBtn, true, "…");
  try {
    if (query) {
      const params = new URLSearchParams({ query, mode: "exact", limit: "50" });
      if (docId) params.set("document_id", docId);
      const data = await fetchJson(`/tools/ngram-search?${params.toString()}`);
      renderNgramSearch(data);
    } else {
      const n = Number(els.ngramsN.value || 2);
      const minFreq = Number(els.ngramsMinFreq.value || 2);
      const params = new URLSearchParams({ n: String(n), min_freq: String(minFreq), limit: "200" });
      if (docId) params.set("document_id", docId);
      const data = await fetchJson(`/tools/ngrams?${params.toString()}`);
      renderNgrams(data);
    }
  } catch (err) {
    toast(`Хатои n-grams: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.ngramsBtn, false, query ? "Ёфтан" : "Сохтан");
  }
}

async function onDelete() {
  const doc = state.selectedDoc;
  if (!doc?.id) return;
  const ok = window.confirm(`Файли «${doc.filename}» (#${doc.id})-ро нест мекунед?`);
  if (!ok) return;

  setBusy(els.deleteBtn, true, "Несткунӣ…");
  try {
    await fetchJson(`/documents/${doc.id}`, { method: "DELETE" });
    toast("Файл нест карда шуд.", "success");
    state.selectedDocId = null;
    state.selectedDoc = null;
    await refreshDocs({ keepSelection: false });
  } catch (err) {
    toast(`Нест карда нашуд: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.deleteBtn, false, "Нест кардан");
  }
}

function onDownload() {
  const doc = state.selectedDoc;
  if (!doc?.id) return;
  // Authorization header is required, so download via fetch -> blob.
  (async () => {
    try {
      const blob = await window.Auth.fetchBlob(`/documents/${doc.id}/file`);
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
      toast(`Хатои зеркашӣ: ${String(err.message || err)}`, "error");
    }
  })();
}

function attachTabEvents() {
  for (const btn of document.querySelectorAll("[data-tab]")) {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  }
}

function attachViewEvents() {
  for (const btn of document.querySelectorAll("[data-view]")) {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  }
}

function attachEvents() {
  els.docFilter.addEventListener("input", renderDocs);
  if (els.docBody) els.docBody.addEventListener("click", onDocBodyClick);
  if (els.openUploadModalBtn) els.openUploadModalBtn.addEventListener("click", () => setModalOpen(true));
  if (els.uploadModalForm) els.uploadModalForm.addEventListener("submit", onUploadModalSubmit);
  if (els.uploadModal) {
    els.uploadModal.addEventListener("click", (e) => {
      if (e.target && e.target.hasAttribute && e.target.hasAttribute("data-modal-close")) setModalOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && els.uploadModal.classList.contains("is-open")) setModalOpen(false);
    });
  }
  if (els.uploadFile) {
    els.uploadFile.addEventListener("change", () => {
      const file = els.uploadFile.files?.[0];
      if (!file) return;
      if (els.metaTitle && !String(els.metaTitle.value || "").trim()) els.metaTitle.value = inferTitleFromFilename(file.name);
      const author = String(els.metaAuthor?.value || "").trim();
      const title = String(els.metaTitle?.value || "").trim();
      const publisher = String(els.metaPublisher?.value || "").trim();
      const year = String(els.metaYear?.value || "").trim();
      if (els.metaBib && !String(els.metaBib.value || "").trim()) {
        els.metaBib.value = buildBibliography({ author, title, publisher, year });
      }
    });
  }
  for (const el of [els.metaAuthor, els.metaTitle, els.metaPublisher, els.metaYear]) {
    if (!el) continue;
    el.addEventListener("input", () => {
      if (!els.metaBib) return;
      const current = String(els.metaBib.value || "").trim();
      if (current) return; // don't overwrite user text
      const author = String(els.metaAuthor?.value || "").trim();
      const title = String(els.metaTitle?.value || "").trim();
      const publisher = String(els.metaPublisher?.value || "").trim();
      const year = String(els.metaYear?.value || "").trim();
      els.metaBib.value = buildBibliography({ author, title, publisher, year });
    });
  }
  els.searchForm.addEventListener("submit", onSearch);
  els.searchTarget.addEventListener("change", () => {
    setWordModeVisibility();
  });
  if (els.concordanceForm) els.concordanceForm.addEventListener("submit", onConcordance);
  if (els.wordlistForm) els.wordlistForm.addEventListener("submit", onWordlist);
  if (els.ngramsForm) els.ngramsForm.addEventListener("submit", onNgrams);
  if (els.ngramsQuery && els.ngramsBtn) {
    els.ngramsQuery.addEventListener("input", () => {
      const query = String(els.ngramsQuery.value || "").trim();
      els.ngramsBtn.textContent = query ? "Ёфтан" : "Сохтан";
    });
  }
  els.downloadBtn.addEventListener("click", onDownload);
  if (els.deleteBtn) els.deleteBtn.addEventListener("click", onDelete);
  attachTabEvents();
  attachViewEvents();
}

async function init() {
  if (!window.Auth?.requireAuthOrRedirect?.()) return;
  try {
    state.me = await window.Auth.me();
  } catch (err) {
    return;
  }

  setAuthNav(state.me);
  setWordModeVisibility();
  setView(state.activeView);
  attachEvents();
  refreshDocs();
}

init();
