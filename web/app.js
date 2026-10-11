(function () {
  "use strict";

  const DATA = window.__DATA__ || { runs: [] };
  const runs = DATA.runs || [];
  let filter = "all";
  let query = "";
  let current = null;
  let step = 0;
  let playing = false;
  let timer = null;

  const $ = (id) => document.getElementById(id);

  function fmtDur(ms) {
    if (ms == null || ms < 0) return "—";
    if (ms < 1000) return ms + " ms";
    const s = Math.round(ms / 1000);
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    const r = s % 60;
    if (m < 60) return m + "m " + r + "s";
    const h = Math.floor(m / 60);
    return h + "h " + (m % 60) + "m";
  }

  function etClock() {
    try {
      return new Date().toLocaleString("en-US", {
        timeZone: "America/New_York",
        weekday: "short",
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      }) + " ET";
    } catch (_) {
      return new Date().toLocaleTimeString();
    }
  }

  function parseHash() {
    const h = (location.hash || "#runs").replace(/^#/, "");
    const parts = h.split("/");
    return { view: parts[0] || "runs", id: parts[1] || null };
  }

  function setHash(view, id) {
    const next = id ? `#${view}/${id}` : `#${view}`;
    if (location.hash !== next) location.hash = next;
    else showView(view, id);
  }

  function showView(view, id) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.view === view;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".view").forEach((v) => {
      v.classList.toggle("active", v.id === "view-" + view);
    });
    if (view === "replay") {
      if (id) {
        const r = runs.find((x) => x.id === id);
        if (r) openReplay(r, false);
        else showEmpty();
      } else if (!current) {
        showEmpty();
      }
    }
  }

  function showEmpty() {
    $("replayEmpty").hidden = false;
    $("replayStage").hidden = true;
    current = null;
  }

  function filtered() {
    const q = query.trim().toLowerCase();
    return runs.filter((r) => {
      if (filter === "demo" && !r.demo) return false;
      if (filter === "error" && r.status !== "error" && !r.demo) return false;
      if (filter === "ok" && (r.status !== "ok" || r.demo)) return false;
      if (!q) return true;
      const hay = `${r.bot || ""} ${r.routine || ""} ${r.slug || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function renderStats() {
    const live = runs.filter((r) => !r.demo);
    const errs = live.filter((r) => r.status === "error").length;
    const sparse = live.filter((r) => r.sparse).length;
    const tools = live.reduce((a, r) => a + ((r.counts && r.counts.tools) || 0), 0);
    $("statsRow").innerHTML = [
      ["Live runs", live.length],
      ["Tool events", tools],
      ["Sparse traces", sparse],
      ["Errors", errs],
    ]
      .map(
        ([l, n]) =>
          `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
      )
      .join("");
  }

  function renderList() {
    const list = filtered();
    const el = $("runList");
    if (!list.length) {
      el.innerHTML = `<div class="empty panel"><p>No runs match this filter.</p></div>`;
      return;
    }
    el.innerHTML = list
      .map((r) => {
        const cls = [
          "run-card",
          r.demo ? "demo" : "",
          r.status === "error" ? "error-run" : "",
        ]
          .filter(Boolean)
          .join(" ");
        const demoTag = r.demo ? `<span class="tag-demo">DEMO</span>` : "";
        const sparse = r.sparse && !r.demo ? " · sparse audit" : "";
        return `<button type="button" class="${cls}" data-id="${escapeAttr(r.id)}">
          <span class="status-dot ${escapeAttr(r.status || "unknown")}" aria-hidden="true"></span>
          <div>
            <h3>${escapeHtml(r.routine || "routine")}${demoTag}</h3>
            <p class="sub">${escapeHtml(r.bot || "?")} · ${escapeHtml(r.trigger || "")}${sparse}</p>
          </div>
          <div class="meta">
            <span>${escapeHtml(r.startedLabel || "—")}</span>
            <span class="counts">${(r.counts && r.counts.events) || 0} steps · ${fmtDur(r.durationMs)}</span>
          </div>
        </button>`;
      })
      .join("");
    el.querySelectorAll(".run-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        const r = runs.find((x) => x.id === btn.dataset.id);
        if (r) setHash("replay", r.id);
      });
    });
  }

  function openReplay(r, pushHash) {
    stopPlay();
    current = r;
    step = 0;
    $("replayEmpty").hidden = true;
    $("replayStage").hidden = false;

    const banner = $("demoBanner");
    if (r.demo && r.banner) {
      banner.hidden = false;
      banner.textContent = r.banner;
    } else {
      banner.hidden = true;
      banner.textContent = "";
    }

    const st = $("rpStatus");
    st.textContent = r.demo ? "DEMO" : r.status || "—";
    st.className = "badge " + (r.demo ? "demo" : r.status === "error" ? "error" : "");
    $("rpBot").textContent = r.bot || "—";
    $("rpTrigger").textContent = r.trigger || "—";
    $("rpTitle").textContent = r.routine || "Run";
    $("rpMeta").textContent = `${r.startedLabel || "—"} → ${r.finishedLabel || "—"} · ${fmtDur(r.durationMs)}`;
    const sum = $("rpSummary");
    if (r.summary) {
      sum.hidden = false;
      sum.textContent = r.summary;
    } else {
      sum.hidden = true;
      sum.textContent = "";
    }
    const c = r.counts || {};
    $("rpCounts").innerHTML = [
      ["Events", c.events || 0],
      ["Tools", c.tools || 0],
      ["Files", c.files || 0],
      ["Errors", c.errors || 0],
    ]
      .map(([l, n]) => `<div><strong>${n}</strong>${l}</div>`)
      .join("");

    const events = r.events || [];
    const scrub = $("scrubber");
    scrub.max = Math.max(0, events.length - 1);
    scrub.value = 0;

    renderRail(events);
    renderTimeline(events);
    selectStep(0);
    if (pushHash !== false) setHash("replay", r.id);
  }

  function renderRail(events) {
    $("rail").innerHTML = events
      .map((e, i) => {
        const k = e.kind || "tool";
        return `<span class="k-${k}" data-i="${i}" title="${escapeAttr(e.label || k)}"></span>`;
      })
      .join("");
  }

  function renderTimeline(events) {
    const el = $("timeline");
    el.innerHTML = events
      .map((e, i) => {
        const k = e.kind || "tool";
        const t = (e.ts || "").slice(11, 19) || "—";
        const ms = e.ms != null ? fmtDur(e.ms) : "";
        return `<div class="tl-item k-${k}" data-i="${i}">
          <span class="tl-dot"></span>
          <div class="tl-body">
            <div class="tl-top">
              <span class="tl-app">${escapeHtml(e.app || k)}</span>
              <span class="tl-time">${escapeHtml(t)}Z</span>
            </div>
            <div class="tl-label">${escapeHtml(e.label || e.type || "event")}</div>
            ${ms ? `<div class="tl-ms">${escapeHtml(ms)}</div>` : ""}
          </div>
        </div>`;
      })
      .join("");
    el.querySelectorAll(".tl-item").forEach((node) => {
      node.addEventListener("click", () => {
        stopPlay();
        selectStep(Number(node.dataset.i));
      });
    });
  }

  function selectStep(i) {
    if (!current) return;
    const events = current.events || [];
    if (!events.length) return;
    step = Math.max(0, Math.min(i, events.length - 1));
    $("scrubber").value = String(step);
    $("stepPos").textContent = `${step + 1} / ${events.length}`;
    $("btnPlay").textContent = playing ? "❚❚" : "▶";

    document.querySelectorAll(".tl-item").forEach((node) => {
      const idx = Number(node.dataset.i);
      node.classList.toggle("active", idx === step);
      node.classList.toggle("dim", idx > step);
    });
    document.querySelectorAll("#rail span").forEach((node) => {
      node.classList.toggle("on", Number(node.dataset.i) <= step);
    });

    const active = document.querySelector(`.tl-item[data-i="${step}"]`);
    if (active) {
      active.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    const e = events[step];
    $("detTitle").textContent = e.label || e.type || "Step";
    const rows = [
      ["Kind", e.kind || "—"],
      ["App", e.app || "—"],
      ["Type", e.type || "—"],
      ["Status", e.status || "—"],
      ["Time (UTC)", e.ts || "—"],
      ["Duration", e.ms != null ? fmtDur(e.ms) : "—"],
    ];
    if (e.path) rows.push(["Path", e.path]);
    if (e.bytes != null) rows.push(["Bytes", String(e.bytes)]);
    if (e.ext) rows.push(["Ext", e.ext]);
    $("detDl").innerHTML = rows
      .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(String(v))}</dd>`)
      .join("");
    const det = $("detDetail");
    if (e.detail) {
      det.hidden = false;
      det.textContent = e.detail;
    } else {
      det.hidden = true;
      det.textContent = "";
    }
  }

  function stopPlay() {
    playing = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    $("btnPlay").textContent = "▶";
  }

  function tick() {
    if (!playing || !current) return;
    const events = current.events || [];
    if (step >= events.length - 1) {
      stopPlay();
      return;
    }
    selectStep(step + 1);
    const speed = Number($("playSpeed").value) || 500;
    timer = setTimeout(tick, speed);
  }

  function togglePlay() {
    if (!current) return;
    if (playing) {
      stopPlay();
      return;
    }
    const events = current.events || [];
    if (step >= events.length - 1) selectStep(0);
    playing = true;
    $("btnPlay").textContent = "❚❚";
    tick();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function boot() {
    const liveN = DATA.liveCount != null ? DATA.liveCount : runs.filter((r) => !r.demo).length;
    const pill = $("dataPill");
    pill.textContent = `${liveN} live · ${runs.some((r) => r.demo) ? "DEMO on" : "no demo"}`;
    pill.classList.add(liveN ? "live" : "warn");

    $("footSrc").textContent = DATA.source || "local snapshot";
    $("aboutStamp").textContent = DATA.generatedAt
      ? `Snapshot generated ${DATA.generatedAt}`
      : "Offline embed";

    function clock() {
      $("clockPill").textContent = etClock();
    }
    clock();
    setInterval(clock, 1000);

    document.querySelectorAll(".tab").forEach((t) => {
      t.addEventListener("click", () => {
        if (t.dataset.view === "replay" && current) setHash("replay", current.id);
        else setHash(t.dataset.view);
      });
    });

    document.querySelectorAll(".chip").forEach((c) => {
      c.addEventListener("click", () => {
        filter = c.dataset.filter;
        document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === c));
        renderList();
      });
    });

    $("runSearch").addEventListener("input", (e) => {
      query = e.target.value || "";
      renderList();
    });

    $("openDemoBtn").addEventListener("click", () => {
      const demo = runs.find((r) => r.demo);
      if (demo) setHash("replay", demo.id);
    });

    $("btnPlay").addEventListener("click", togglePlay);
    $("btnPrev").addEventListener("click", () => {
      stopPlay();
      selectStep(step - 1);
    });
    $("btnNext").addEventListener("click", () => {
      stopPlay();
      selectStep(step + 1);
    });
    $("scrubber").addEventListener("input", (e) => {
      stopPlay();
      selectStep(Number(e.target.value));
    });
    $("rail").addEventListener("click", (e) => {
      const span = e.target.closest("span[data-i]");
      if (!span) return;
      stopPlay();
      selectStep(Number(span.dataset.i));
    });

    window.addEventListener("hashchange", () => {
      const { view, id } = parseHash();
      showView(view, id);
    });

    renderStats();
    renderList();

    const { view, id } = parseHash();
    if (!location.hash) location.hash = "#runs";
    showView(view, id);

    // For screenshots / deep links: if #replay without id, keep empty;
    // if #runs and we want hero later, screenshot script deep-links demo.
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
