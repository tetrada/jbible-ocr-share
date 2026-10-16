/* Private JBible source-to-verse review. Only the authenticated local service. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let cases = [], reviews = {}, visible = [], current = null, choice = "uncertain";
  let previewPage = 31, focusY = 0.5, zoom = 1.45, loading = false;
  const images = new Map();
  const asText = v => String(v == null ? "" : v);
  const toFixed = v => typeof v === "number" ? v.toFixed(3) : "not located";
  const readNumber = id => {
    const raw = $(id).value.trim();
    return raw === "" ? null : Number(raw);
  };
  const reviewed = r => !!(r && r.choice && r.choice !== "uncertain");
  const label = c => "P" + c.page + " " + c.side + " · " + c.margin_raw_line;

  function elem(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = asText(text);
    return node;
  }
  function tag(container, value, warning) {
    const item = elem("span", warning ? "tag warning" : "tag", value);
    container.appendChild(item);
  }
  function filtered() {
    const mode = $("filter").value;
    let list = cases.filter(c =>
      mode === "all" || (mode === "pending" && !reviewed(reviews[c.link_id])) ||
      (mode === "done" && reviewed(reviews[c.link_id])) ||
      (mode === "candidates" && c.state === "PROPOSED_REVIEW_REQUIRED") ||
      (mode === "reviews" && c.state !== "PROPOSED_REVIEW_REQUIRED")
    );
    if (mode === "pending") list = list.concat(cases.filter(c => reviewed(reviews[c.link_id])));
    return list;
  }
  function nav() {
    visible = filtered();
    $("queue").replaceChildren();
    for (const c of visible) {
      const b = elem("button", (current && current.link_id === c.link_id ? "active " : "") +
        (reviewed(reviews[c.link_id]) ? "complete" : ""));
      b.type = "button";
      b.appendChild(elem("span", "qpage", "P" + c.page + " " + c.side));
      b.appendChild(elem("span", "qtext", c.target_printed));
      b.appendChild(elem("span", "qmark", reviewed(reviews[c.link_id]) ? "✓" : "○"));
      b.onclick = () => show(c);
      $("queue").appendChild(b);
    }
    const done = cases.filter(c => reviewed(reviews[c.link_id])).length;
    $("progress").textContent = done + " reviewed / " + cases.length + " source rows";
  }
  function imageUrl(page) {
    return "../api/image/" + String(page).padStart(4, "0") + ".jpg";
  }
  function loadImage(page) {
    if (images.has(page)) return images.get(page);
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    const record = { img, status: "loading" };
    images.set(page, record);
    img.onload = () => { record.status = "ready"; draw(); };
    img.onerror = () => { record.status = "error"; draw(); };
    img.src = imageUrl(page);
    return record;
  }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
  function draw() {
    const cvs = $("scan");
    const ctx = cvs.getContext("2d");
    ctx.clearRect(0, 0, cvs.width, cvs.height);
    ctx.fillStyle = "#e5dcd0"; ctx.fillRect(0, 0, cvs.width, cvs.height);
    if (!current) return;
    $("viewPage").textContent = "Page " + previewPage;
    $("zoomText").textContent = zoom.toFixed(2) + "×";
    const rec = loadImage(previewPage);
    if (rec.status !== "ready") {
      ctx.fillStyle = "#695b4c"; ctx.font = "23px sans-serif";
      ctx.fillText(rec.status === "error" ? "Unable to load protected scan" : "Loading scan…", 65, 90);
      return;
    }
    const im = rec.img, w = im.naturalWidth, h = im.naturalHeight;
    const side = current.side;
    const sx = side === "L" ? 0 : Math.floor(w / 2);
    const sw = side === "L" ? Math.floor(w / 2) : w - sx;
    // Zoom changes the vertical span, preserving scan aspect ratio and coordinates.
    const sourceH = clamp(sw * cvs.height / cvs.width / zoom, 1, h);
    const ystart = clamp(focusY * h - sourceH / 2, 0, h - sourceH);
    ctx.drawImage(im, sx, ystart, sw, sourceH, 0, 0, cvs.width, cvs.height);
    if (previewPage !== current.page) return;
    const markers = [
      {y: current.y_fraction, color: "#bf4733", title: "MARGIN"},
      {y: current.source && current.source.source_marker_y_fraction, color: "#16834d", title: "SOURCE"}
    ];
    for (const m of markers) {
      if (typeof m.y !== "number") continue;
      const yy = (m.y * h - ystart) / sourceH * cvs.height;
      if (yy < -10 || yy > cvs.height + 10) continue;
      ctx.strokeStyle = m.color; ctx.lineWidth = 3;
      ctx.setLineDash([13, 7]); ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(cvs.width, yy); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = m.color; ctx.fillRect(0, clamp(yy - 28, 0, cvs.height-27), 116, 27);
      ctx.font = "bold 15px sans-serif"; ctx.fillStyle = "white";
      ctx.fillText(m.title, 9, clamp(yy - 10, 18, cvs.height - 9));
    }
  }
  function changePreview(page) {
    if (page < 31 || page > 40) return;
    previewPage = page;
    draw();
  }
  function sourceOf(c) {
    const s = c.source || {};
    return [s.source_book_code || "?", s.source_chapter || "?",
      s.source_verse || "?"].join(" / ");
  }
  function updateChoice() {
    for (const b of document.querySelectorAll("[data-choice]"))
      b.classList.toggle("selected", b.dataset.choice === choice);
  }
  function show(c) {
    current = c;
    previewPage = c.page;
    $("reviewPanel").hidden = false;
    $("loading").hidden = true;
    $("caseTitle").textContent = "Page " + c.page + " · " +
      (c.side === "L" ? "left" : "right") + " · " + c.row_id;
    $("caseDetail").textContent = "One source → one destination · " + c.row_id +
      " · segment #" + c.target_segment_index + " · " + c.state +
      " · margin y=" + toFixed(c.y_fraction);
    $("marginRaw").textContent = c.target_printed || "(unparsed destination)";
    $("targetTags").replaceChildren();
    const p = c.target || {};
    const coord = p.book_code ? p.book_code + " " + asText(p.chapter) + ":" +
      (p.verse != null ? p.verse : p.verses ? p.verses.join(",") :
       p.type === "CHAPTER_ONLY" ? "(chapter)" : p.type === "CHAPTER_RANGE" ? "(chapters)" : "—")
      : "Unresolved target book";
    tag($("targetTags"), coord, !p.book_code || c.target_reason !== "OCR_TARGET_NOT_SCAN_VERIFIED");
    $("targetDetails").textContent = "Destination " + c.target_segment_index +
      " of " + cases.filter(x => x.row_id === c.row_id).length +
      " from printed margin row · " + c.target_reason;
    const s = c.source || {};
    $("sourceSummary").textContent = sourceOf(c) + " · " + asText(s.scope || "UNKNOWN");
    $("sourceTags").replaceChildren();
    tag($("sourceTags"), asText(c.source_reason), c.source_reason !== "PROPOSED_NEEDS_HUMAN_REVIEW");
    tag($("sourceTags"), asText(s.alignment_evidence || "No visual evidence"), s.alignment_evidence !== "VERSE_MARKER_AND_TEXT");
    tag($("sourceTags"), "Confidence: " + asText(s.confidence || "unknown"), true);
    $("sourceEvidence").textContent = "Visible text: " + asText(s.source_text_evidence || "(not recorded)") +
      " · " + asText(s.reason || "");
    const ctxt = c.page_context || null;
    const pageStart = ctxt && ctxt.page_start_chapter != null ?
      " · starts " + ctxt.page_start_chapter + ":" + ctxt.page_start_verse : "";
    $("contextHint").textContent = ctxt ?
      "Page book: " + ctxt.source_book_code + pageStart +
      " (from page registry; check this page or book boundary)." +
      (c.page_model_book_conflict ? " WARNING: model and registry disagree." : "") :
      "No page-level source book registered. Check the printed header.";
    const r = reviews[c.link_id] || {};
    const saved = r.source || {};
    $("book").value = saved.book_code || c.book_for_review || "";
    $("chapter").value = saved.chapter != null ? saved.chapter : (s.source_chapter || "");
    $("verse").value = saved.verse != null ? saved.verse : (s.source_verse || "");
    $("endChapter").value = saved.end_chapter != null ? saved.end_chapter : (s.source_end_chapter || "");
    $("endVerse").value = saved.end_verse != null ? saved.end_verse : (s.source_end_verse || "");
    $("scope").value = saved.scope || s.scope || "UNKNOWN";
    $("bookBasis").value = saved.source_book_basis || (
      ctxt ? "PAGE_REGISTRY" :
      s.source_book_evidence === "HEADER_VISIBLE" || s.source_book_evidence === "CHAPTER_TITLE_VISIBLE"
        ? "PRINTED_THIS_PAGE" : "UNKNOWN");
    $("targetText").value = r.target_printed || c.target_printed;
    $("notes").value = r.notes || "";
    const ch = r.checked || {};
    $("sourceChecked").checked = ch.source_marker === true;
    $("targetChecked").checked = ch.target_print === true;
    $("alignmentChecked").checked = ch.alignment === true;
    $("pageChecked").checked = ch.page_book === true;
    choice = r.choice || "uncertain";
    updateChoice();
    $("feedback").textContent = "";
    focusY = clamp((c.y_fraction != null ? c.y_fraction : 0.5) * 0.7 +
      (typeof s.source_marker_y_fraction === "number" ? s.source_marker_y_fraction : c.y_fraction || 0.5) * 0.3, 0, 1);
    zoom = 1.45;
    $("yMove").value = String(Math.round(focusY * 1000));
    nav();
    draw();
  }
  function adjacent(delta) {
    if (!current) return;
    const at = visible.findIndex(c => c.link_id === current.link_id);
    if (at < 0 || !visible.length) return;
    show(visible[clamp(at + delta, 0, visible.length - 1)]);
  }
  async function save(next) {
    if (!current || loading) return;
    const payload = {
      link_id: current.link_id,
      row_id: current.row_id, target_segment_index: current.target_segment_index,
      choice,
      source: {
        book_code: $("book").value.trim(),
        chapter: readNumber("chapter"), verse: readNumber("verse"),
        end_chapter: readNumber("endChapter"), end_verse: readNumber("endVerse"),
        scope: $("scope").value, source_book_basis: $("bookBasis").value
      },
      target_printed: $("targetText").value,
      checked: {source_marker:$("sourceChecked").checked,
                target_print:$("targetChecked").checked,
                alignment:$("alignmentChecked").checked,
                page_book:$("pageChecked").checked},
      notes: $("notes").value
    };
    $("feedback").textContent = "Saving…";
    loading = true;
    try {
      const response = await fetch("../api/link-review", {
        method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json","X-JBible-Review":"1"},
        body:JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw Error(data.error || "Save failed");
      reviews[current.link_id] = data.review;
      const old = current.link_id;
      nav();
      $("feedback").textContent = "Saved securely. No SQL or automatic Bible link import.";
      if (next) {
        // Continue to next *unreviewed* row, not repeatedly to the same case.
        const pos = visible.findIndex(x => x.link_id === old);
        const unreviewed = visible.slice(pos+1).find(x => !reviewed(reviews[x.link_id])) ||
          visible.slice(0,pos).find(x => !reviewed(reviews[x.link_id]));
        const target = unreviewed || visible[Math.min(pos+1, visible.length-1)];
        if (target && target.link_id !== old) show(target);
      }
    } catch (e) {
      $("feedback").textContent = "Could not save: " + asText(e.message);
    } finally { loading = false; }
  }
  function bind() {
    $("filter").addEventListener("change", nav);
    $("prev").onclick = () => adjacent(-1);
    $("next").onclick = () => adjacent(1);
    $("zoomOut").onclick = () => {zoom = clamp(zoom/1.28, .65, 6); draw();};
    $("zoomIn").onclick = () => {zoom = clamp(zoom*1.28, .65, 6); draw();};
    $("yMove").oninput = () => {focusY = Number($("yMove").value)/1000; draw();};
    $("neighborPrev").onclick = () => changePreview(previewPage-1);
    $("neighborNext").onclick = () => changePreview(previewPage+1);
    $("fullPage").onclick = () => {
      $("dialogTitle").textContent = "Original page " + previewPage;
      $("fullImg").src = imageUrl(previewPage);
      $("fullDialog").showModal();
    };
    $("closeDialog").onclick = () => $("fullDialog").close();
    for (const b of document.querySelectorAll("[data-choice]"))
      b.onclick = () => { choice=b.dataset.choice; updateChoice(); };
    $("save").onclick = () => save(false);
    $("saveNext").onclick = () => save(true);
  }
  async function init() {
    bind();
    try {
      const response = await fetch("../api/link-cases",{credentials:"same-origin",cache:"no-store"});
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.cases)) throw Error(data.error || "Could not load");
      cases = data.cases; reviews = data.reviews || {};
      if (!cases.length) throw Error("No source-link results yet. Publish and install the pilot first.");
      nav();
      show(cases.find(c => !reviewed(reviews[c.link_id])) || cases[0]);
    } catch(e) {
      $("loading").textContent = "Review queue unavailable: " + asText(e.message);
      $("progress").textContent = "Unavailable";
    }
  }
  init();
})();
