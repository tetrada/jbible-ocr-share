/* JBible human scan review UI. No third-party services; authenticated same-origin API. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let cases = [], reviews = {}, index = 0, choice = null, dirty = false;
  const loadedImages = new Map();
  let zoom = 2.5, offset = 0, generation = 0;

  const lines = rows => (rows || []).map(r => r.raw_line || "").filter(Boolean);
  const textFor = rows => lines(rows).join("\n");
  const escapeText = s => String(s == null ? "" : s);
  const readLines = () => $("corrected").value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const isConfirmed = r => !!(r && r.verified_against_scan);
  const caseName = c => "Page " + c.page + " · " + (c.side === "L" ? "left" : "right") + " margin";
  const pageUrl = c => "api/image/" + String(c.page).padStart(4, "0") + ".jpg";

  function median(numbers) {
    if (!numbers.length) return 0.5;
    numbers.sort((a, b) => a - b);
    return numbers.length % 2 ? numbers[(numbers.length - 1) / 2] :
      (numbers[numbers.length / 2 - 1] + numbers[numbers.length / 2]) / 2;
  }

  function caseY(c) {
    const values = [...(c.v2 || []), ...(c.v3 || [])].map(x => x.y_fraction)
      .filter(x => typeof x === "number" && x >= 0 && x <= 1);
    return median(values);
  }

  function updateNav() {
    $("caseNav").replaceChildren();
    cases.forEach((c, n) => {
      const r = reviews[c.case_id];
      const button = document.createElement("button");
      button.type = "button";
      button.className = "casebutton" + (n === index ? " active" : "") +
        (isConfirmed(r) ? " complete" : "");
      button.innerHTML = '<span class="number">' + escapeText(c.case_id) +
        '</span><span class="name">Page ' + c.page + " · " + c.side +
        '</span><span class="state">' + (isConfirmed(r) ? "✓" : (r ? "◷" : "○")) + "</span>";
      button.onclick = () => go(n);
      $("caseNav").appendChild(button);
    });
    const complete = Object.values(reviews).filter(isConfirmed).length;
    $("progress").textContent = complete + " of " + cases.length + " confirmed";
  }

  function updateChoice() {
    for (const v of ["v2", "v3", "neither", "uncertain"]) {
      const node = $(v + "Choice");
      node.classList.toggle("selected", choice === v);
      $(v + "Mark").textContent = choice === v ? "✓ SELECTED" : "";
    }
    if (choice === "uncertain") {
      $("confirmed").checked = false;
      $("confirmed").disabled = true;
    } else {
      $("confirmed").disabled = false;
    }
  }

  function choose(v) {
    choice = v;
    const c = cases[index];
    if (v === "v2") $("corrected").value = textFor(c.v2);
    if (v === "v3") $("corrected").value = textFor(c.v3);
    if (v === "uncertain") $("corrected").value = "";
    dirty = true;
    updateChoice();
    $("feedback").textContent = "";
  }

  function show(n) {
    index = n;
    const c = cases[index];
    const review = reviews[c.case_id] || {};
    dirty = false;
    choice = review.choice || null;
    offset = 0;
    zoom = 2.5;
    $("zoom").value = String(zoom);
    $("caseTitle").textContent = c.case_id + " · " + caseName(c);
    $("caseSubtitle").textContent = c.issue + " · exact typeface / printed rows matter";
    const agreement = c.matching_text_is_not_accuracy === true;
    $("v2Choice").querySelector(".top").firstChild.nodeValue =
      agreement ? "Both OCR versions agree (not verified) " : "V2 original OCR ";
    $("v3Choice").style.display = agreement ? "none" : "";
    $("v2Text").textContent = textFor(c.v2) || "(no reference detected)";
    $("v3Text").textContent = textFor(c.v3) || "(no reference detected)";
    $("corrected").value = (review.corrected_lines || []).join("\n");
    $("notes").value = review.notes || "";
    $("confirmed").checked = !!review.verified_against_scan;
    $("feedback").textContent = review.saved_at_utc ? "Previously saved · " +
      new Date(review.saved_at_utc).toLocaleString() : "";
    $("prevBtn").disabled = index === 0;
    $("nextBtn").disabled = index === cases.length - 1;
    $("scanHint").textContent = "Printed reference around " +
      Math.round(100 * caseY(c)) + "% down the page";
    updateChoice();
    updateNav();
    redraw();
  }

  function go(n) {
    if (n < 0 || n >= cases.length || n === index) return;
    if (dirty && !window.confirm("You have unsaved changes. Leave this case?")) return;
    show(n);
  }

  function redraw() {
    const c = cases[index];
    if (!c) return;
    const request = ++generation;
    const key = String(c.page);
    const src = pageUrl(c);
    const canvas = $("scanCanvas");
    const ctx = canvas.getContext("2d");
    const img = loadedImages.get(key);
    if (!img) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#5f594d";
      ctx.font = "19px system-ui";
      ctx.fillText("Loading original scanned page…", 32, 50);
      const image = new Image();
      image.onload = () => {
        loadedImages.set(key, image);
        if (request === generation) redraw();
      };
      image.onerror = () => {
        if (request !== generation) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillText("Cannot load scan image. Check VPS file permissions.", 30, 50);
      };
      image.src = src;
      return;
    }
    const halfWidth = img.naturalWidth / 2;
    const srcX = c.side === "L" ? 0 : halfWidth;
    const srcW = halfWidth;
    const srcH = Math.min(img.naturalHeight, img.naturalHeight * 0.43 / zoom);
    const center = Math.max(srcH / 2, Math.min(img.naturalHeight - srcH / 2,
      img.naturalHeight * (caseY(c) + offset)));
    const srcY = center - srcH / 2;
    canvas.width = 1100;
    canvas.height = Math.max(200, Math.min(850, Math.round(1100 * srcH / srcW)));
    ctx.fillStyle = "#e7dfd1";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, srcX, srcY, srcW, srcH,
                  0, 0, canvas.width, canvas.height);
    $("scanHint").textContent = "Margin " + c.side + " · position ~" +
      Math.round((caseY(c) + offset) * 100) + "% · estimated";
  }

  async function save() {
    const c = cases[index];
    if (!choice) {
      $("feedback").textContent = "Choose V2, V3, Neither, or Unsure first.";
      return;
    }
    const payload = {
      case_id: c.case_id, choice,
      corrected_lines: choice === "uncertain" ? [] : readLines(),
      notes: $("notes").value,
      verified_against_scan: choice !== "uncertain" && $("confirmed").checked
    };
    if (choice !== "uncertain" && !payload.corrected_lines.length) {
      $("feedback").textContent = "Please enter the printed reference text, one row per line.";
      return;
    }
    $("saveBtn").disabled = true;
    $("feedback").textContent = "Saving…";
    try {
      const response = await fetch("api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-JBible-Review": "1" },
        body: JSON.stringify(payload),
        credentials: "same-origin"
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Server rejected review");
      reviews[c.case_id] = result.review;
      dirty = false;
      updateNav();
      $("feedback").textContent = "Saved! Text corrections will sync to Git automatically.";
      if (index < cases.length - 1) {
        setTimeout(() => { if (!dirty && cases[index].case_id === c.case_id) show(index + 1); }, 480);
      }
    } catch (err) {
      $("feedback").textContent = "Save failed: " + err.message;
    } finally {
      $("saveBtn").disabled = false;
    }
  }

  function fullPage() {
    const c = cases[index];
    $("fullTitle").textContent = caseName(c) + " · original full-page scan";
    $("fullImg").src = pageUrl(c);
    const dialog = $("fullDialog");
    if (dialog.showModal) dialog.showModal();
  }

  async function init() {
    try {
      const response = await fetch("api/cases", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Could not load cases (HTTP " + response.status + ")");
      const data = await response.json();
      cases = data.priorities || [];
      reviews = data.reviews || {};
      if (!cases.length) throw new Error("No scan-review cases found");
      for (const v of ["v2", "v3", "neither", "uncertain"]) {
        $(v + "Choice").onclick = () => choose(v);
      }
      $("saveBtn").onclick = save;
      $("prevBtn").onclick = () => go(index - 1);
      $("nextBtn").onclick = () => go(index + 1);
      $("moveUp").onclick = () => { offset -= .028; redraw(); };
      $("moveDown").onclick = () => { offset += .028; redraw(); };
      $("zoom").oninput = ev => { zoom = Number(ev.target.value); redraw(); };
      $("fullBtn").onclick = fullPage;
      $("closeFull").onclick = () => $("fullDialog").close();
      for (const name of ["corrected", "notes", "confirmed"]) {
        $(name).addEventListener("input", () => { dirty = true; });
      }
      document.addEventListener("keydown", ev => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
          ev.preventDefault();
          save();
        }
      });
      show(0);
    } catch (err) {
      $("caseTitle").textContent = "Unable to load the review page";
      $("caseSubtitle").textContent = err.message;
      $("progress").textContent = "Unavailable";
    }
  }

  init();
})();
