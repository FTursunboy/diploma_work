/* eslint-disable no-alert */
const state = {
  docs: [],
  docsById: new Map(),
  selectedDocId: null,
  selectedDoc: null,
  activeView: "search",
  activeTab: "text",
  wordFreqByDocId: new Map(),
  renderLimits: {
    paragraphs: 50,
    sentences: 50,
    words: 200,
  },
};

const els = {
  docsMeta: document.getElementById("docsMeta"),
  docFilter: document.getElementById("docFilter"),
  docsList: document.getElementById("docsList"),
  uploadForm: document.getElementById("uploadForm"),
  uploadFile: document.getElementById("uploadFile"),
  uploadBtn: document.getElementById("uploadBtn"),
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
  wordlistDocument: document.getElementById("wordlistDocument"),
  wordlistMinFreq: document.getElementById("wordlistMinFreq"),
  wordlistBtn: document.getElementById("wordlistBtn"),
  ngramsForm: document.getElementById("ngramsForm"),
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
  els.toast.textContent = message;
  els.toast.dataset.type = type;
  els.toast.classList.add("is-visible");
  window.clearTimeout(toast._t);
  toast._t = window.setTimeout(() => els.toast.classList.remove("is-visible"), 3200);
}

async function fetchJson(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const detail = text || res.statusText || "Хатои дархост";
    throw new Error(detail);
  }
  return res.json();
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = !!busy;
  if (label) button.textContent = label;
}

function normalizeStatus(status) {
  if (status === "parsed") return "Тайёр";
  if (status === "uploaded") return "Боргузорӣ шуд";
  if (status === "error") return "Хато";
  return status || "—";
}

function docDisplayName(doc) {
  const base = doc?.filename || `Файл #${doc?.id ?? "?"}`;
  return `${base}`;
}

function updateDocsMeta() {
  els.docsMeta.textContent = `${state.docs.length} файл`;
}

function renderDocs() {
  const filter = (els.docFilter.value || "").trim().toLowerCase();
  const docs = filter
    ? state.docs.filter((d) => docDisplayName(d).toLowerCase().includes(filter))
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
        <div class="docitem__name">${escapeHtml(doc.filename)}</div>
        <div class="badge badge--${escapeHtml(doc.status)}">${escapeHtml(normalizeStatus(doc.status))}</div>
      </div>
      <div class="docitem__meta">#${doc.id} • ${escapeHtml(doc.file_type || "—")}</div>
    `;
    item.addEventListener("click", () => selectDoc(doc.id));
    els.docsList.appendChild(item);
  }
}

function renderDocSelect(selectEl) {
  if (!selectEl) return;
  const current = selectEl.value;
  const options = [
    { value: "", label: "Ҳамаи файлҳо" },
    ...state.docs.map((d) => ({ value: String(d.id), label: `#${d.id} — ${d.filename}` })),
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
  const form = new FormData();
  form.append("file", file);
  return fetchJson("/documents/upload", { method: "POST", body: form });
}

async function onUpload(e) {
  e.preventDefault();
  const file = els.uploadFile.files?.[0];
  if (!file) return toast("Файли PDF/DOCX-ро интихоб кунед.", "warning");

  setBusy(els.uploadBtn, true, "Боргузорӣ…");
  try {
    const doc = await uploadDocument(file);
    toast("Файл боргузорӣ ва коркард шуд.", "success");
    await refreshDocs({ keepSelection: true });
    if (doc?.id) await selectDoc(doc.id);
  } catch (err) {
    toast(`Хатои боргузорӣ: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.uploadBtn, false, "Боргузорӣ");
    els.uploadForm.reset();
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

  els.docStats.innerHTML = `
    <div class="stat"><div class="stat__k">Ҳолат</div><div class="stat__v">${escapeHtml(status)}</div></div>
    <div class="stat"><div class="stat__k">Бандҳо</div><div class="stat__v">${paragraphsCount}</div></div>
    <div class="stat"><div class="stat__k">Ҷумлаҳо</div><div class="stat__v">${sentencesCount}</div></div>
    <div class="stat"><div class="stat__k">Калимаҳо</div><div class="stat__v">${wordsCount}</div></div>
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

  els.docTitle.textContent = docDisplayName(doc);
  renderStats(doc);

  let html = "";
  if (state.activeTab === "text") html = renderDocText(doc);
  if (state.activeTab === "paragraphs") html = renderParagraphs(doc);
  if (state.activeTab === "sentences") html = renderSentences(doc);
  if (state.activeTab === "words") html = renderWords(doc);

  els.docBody.innerHTML = html;
  els.downloadBtn.disabled = false;
  els.deleteBtn.disabled = false;

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
    const docName = doc?.filename || `Файл #${r.document_id}`;
    const p = r.paragraph_index != null ? `Банд ${r.paragraph_index}` : null;
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
    card.addEventListener("click", () => selectDoc(r.document_id));
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
    const docName = it?.filename || `Файл #${it?.document_id ?? "?"}`;
    const p = it?.paragraph_index != null ? `Банд ${it.paragraph_index}` : null;
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
    card.addEventListener("click", () => selectDoc(it.document_id));
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
    setBusy(els.concordanceBtn, false, "Намоиш");
  }
}

function renderWordlist(data, filterText) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const filter = String(filterText || "").trim().toLowerCase();
  const shown = items.filter((it) => !filter || String(it.word || "").toLowerCase().includes(filter));

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
      els.searchWordMode.value = "exact";
      els.searchDocument.value = sourceDocId;
      setView("search");
      try {
        await performSearch({ query: word, target: "word", documentId: sourceDocId || null, mode: "exact" });
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

async function onNgrams(e) {
  e.preventDefault();
  const docId = els.ngramsDocument.value;
  const n = Number(els.ngramsN.value || 2);
  const minFreq = Number(els.ngramsMinFreq.value || 2);
  const params = new URLSearchParams({ n: String(n), min_freq: String(minFreq), limit: "200" });
  if (docId) params.set("document_id", docId);

  setBusy(els.ngramsBtn, true, "…");
  try {
    const data = await fetchJson(`/tools/ngrams?${params.toString()}`);
    renderNgrams(data);
  } catch (err) {
    toast(`Хатои n-grams: ${String(err.message || err)}`, "error");
  } finally {
    setBusy(els.ngramsBtn, false, "Сохтан");
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

  const link = document.createElement("a");
  link.href = `/documents/${doc.id}/file`;
  link.download = doc.filename || "";
  link.rel = "noreferrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
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
  els.uploadForm.addEventListener("submit", onUpload);
  els.searchForm.addEventListener("submit", onSearch);
  els.searchTarget.addEventListener("change", () => {
    setWordModeVisibility();
  });
  if (els.concordanceForm) els.concordanceForm.addEventListener("submit", onConcordance);
  if (els.wordlistForm) els.wordlistForm.addEventListener("submit", onWordlist);
  if (els.ngramsForm) els.ngramsForm.addEventListener("submit", onNgrams);
  els.downloadBtn.addEventListener("click", onDownload);
  els.deleteBtn.addEventListener("click", onDelete);
  attachTabEvents();
  attachViewEvents();
}

function init() {
  setWordModeVisibility();
  setView(state.activeView);
  attachEvents();
  refreshDocs();
}

init();
