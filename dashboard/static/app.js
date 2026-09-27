/* HUD controller: polls /api/state every 2s and renders the panels.
 * Every number shown comes from the API; nothing is estimated or animated.
 *
 * Plugin hooks (see dashboard/plugins/__init__.py):
 *   HQ.onState(fn)      fn(state) after every successful poll
 *   HQ.slots.topbar     element in the top bar for plugin stats/buttons
 *   HQ.slots.banner     full-width strip under the top bar (e.g. goal bars)
 *   HQ.util             { esc, money, label, clock }
 */
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const POLL_MS = 2000;
  let openAgent = null;
  let lastEventSig = "";
  let lastApprovalSig = null;
  let lastState = null;
  let pluginsLoaded = false;
  const stateHooks = [];

  // ------------------------------------------------------------ formatting
  function money(cents) {
    const n = Number(cents) || 0;
    const abs = Math.abs(n);
    const s = (Math.floor(abs / 100)).toLocaleString("en-US") + "." + String(abs % 100).padStart(2, "0");
    return (n < 0 ? "-$" : "$") + s;
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function clock(ts) {
    if (!ts) return "--";
    const d = new Date(ts);
    if (isNaN(d)) return esc(ts);
    const hms = d.toLocaleTimeString("en-GB", { hour12: false });
    const today = new Date().toDateString() === d.toDateString();
    return today ? hms : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hms}`;
  }
  function ago(ts) {
    if (!ts) return "never";
    const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
    if (isNaN(s)) return esc(ts);
    if (s < 60) return `${Math.floor(s)}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }
  const label = s => String(s ?? "").replace(/_/g, " ").toUpperCase();

  window.HQ = {
    onState(fn) { stateHooks.push(fn); if (lastState) fn(lastState); },
    slots: { topbar: $("plugin-topbar"), banner: $("plugin-banner") },
    util: { esc, money, label, clock },
  };

  // ------------------------------------------------------------ plugins
  function loadPlugins(list) {
    if (pluginsLoaded) return;
    pluginsLoaded = true;
    for (const p of list || []) {
      for (const href of p.styles || []) {
        document.head.appendChild(Object.assign(document.createElement("link"), { rel: "stylesheet", href }));
      }
      for (const src of p.scripts || []) {
        document.body.appendChild(Object.assign(document.createElement("script"), { src, async: false }));
      }
    }
  }

  // ------------------------------------------------------------ top bar
  function renderTop(state) {
    $("working-count").textContent = `${state.working_count}/${state.agents.length}`;
    const pending = (state.counts.approvals || {}).pending || 0;
    const el = $("pending-count");
    el.textContent = pending;
    el.classList.toggle("hot", pending > 0);
    if (state.project) {
      $("brand-name").textContent = String(state.project).toUpperCase();
      document.title = `${state.project} // HQ`;
      Station.setTitle(state.project);
    }
  }

  // ------------------------------------------------------------ roster
  function renderRoster(agents) {
    $("roster").innerHTML = agents.map(a => `
      <li data-id="${esc(a.id)}" class="${a.id === openAgent ? "sel" : ""}" title="${esc(a.role)}">
        <span class="dot ${esc(a.status)}"></span>
        <span class="name" style="color:${Station.colorOf(a.id)}">${esc(a.name)}</span>
        <span class="sub"><span class="st-${esc(a.status)}">${label(a.status)}</span>${a.current_task && a.status !== "offline" ? " &middot; " + esc(a.current_task) : ""}</span>
      </li>`).join("");
  }

  // ------------------------------------------------------------ events
  function eventItem(e, withWho = true) {
    const lv = ["info", "success", "warn", "error"].includes(e.level) ? e.level : "info";
    return `<li class="lv-${lv}"><span class="ts">${clock(e.ts)}</span>${withWho && e.agent_id ? `<span class="who">${esc(String(e.agent_id).toUpperCase())}</span>` : ""}${esc(e.message)}</li>`;
  }
  function renderEvents(events) {
    const sig = events.length ? events[0].id + ":" + events.length : "none";
    if (sig === lastEventSig) return;
    lastEventSig = sig;
    $("events").innerHTML = events.length ? events.map(e => eventItem(e)).join("")
      : `<li class="empty">No events yet. Agents report with python -m hq.report.</li>`;
  }

  // ------------------------------------------------------------ status strip
  function renderPipeline(state) {
    const byStatus = {};
    for (const a of state.agents) byStatus[a.status] = (byStatus[a.status] || 0) + 1;
    const chips = obj => Object.entries(obj).map(([k, n]) =>
      `<span class="chip${n ? "" : " muted"}">${esc(label(k))} <b>${n}</b></span>`).join("");
    const ap = state.counts.approvals || {};
    $("pipeline").innerHTML =
      `<div class="grp"><span>CREW</span>${chips(byStatus)}</div>` +
      `<div class="grp"><span>APPROVALS</span>${chips(ap)}</div>`;
    const n = ap.pending || 0;
    const badge = $("approval-count");
    badge.textContent = n; badge.classList.toggle("hot", n > 0);
  }

  // ------------------------------------------------------------ approvals
  async function refreshApprovals() {
    let data;
    try { data = await (await fetch("/api/approvals", { cache: "no-store" })).json(); } catch { return; }
    const items = data.items || [];
    const sig = items.map(d => d.id + ":" + d.title).join(",");
    if (sig === lastApprovalSig) return;
    lastApprovalSig = sig;
    const list = $("approvals");
    if (!items.length) { list.innerHTML = `<div class="empty">Queue empty &mdash; nothing waiting for you.</div>`; return; }
    list.innerHTML = items.map(d => `
      <article class="card" data-id="${d.id}">
        <div class="thumb">${d.image_url ? `<img src="${esc(d.image_url)}" alt="${esc(d.title)}" loading="lazy">` : `<span class="kind-tag">${esc(label(d.kind))}</span>`}</div>
        <div class="title-row"><span class="title">#${d.id} ${esc(d.title)}</span>
          <button class="btn-edit" data-act="edit" title="Edit the title before approving">EDIT</button></div>
        <input class="title-input" type="text" maxlength="255" value="${esc(d.title)}" data-orig="${esc(d.title)}" aria-label="Edited title" hidden>
        <div class="meta">${esc(label(d.kind))}${d.score != null ? ` &middot; SCORE <b>${esc(d.score)}</b>` : ""}${d.submitted_by ? ` &middot; FROM ${esc(label(d.submitted_by))}` : ""}</div>
        ${d.summary ? `<div class="summary">${esc(d.summary)}</div>` : ""}
        ${d.link_url ? `<a class="link" href="${esc(d.link_url)}" target="_blank" rel="noopener noreferrer">OPEN &#8599;</a>`
          : d.link ? `<div class="summary dim">${esc(d.link)}</div>` : ""}
        <input class="note-input" type="text" maxlength="2000" placeholder="note for the crew (optional)" aria-label="Review note">
        <div class="actions">
          <button class="btn-approve" data-act="approve">APPROVE</button>
          <button class="btn-reject" data-act="reject">REJECT</button>
        </div>
        <div class="err lv-error"></div>
      </article>`).join("");
    list.querySelectorAll(".thumb img").forEach(img => img.addEventListener("error", () => {
      img.replaceWith(Object.assign(document.createElement("span"), { className: "empty", textContent: "image unavailable" }));
    }));
  }

  function toggleEdit(card) {
    const input = card.querySelector(".title-input");
    const btn = card.querySelector(".btn-edit");
    input.hidden = !input.hidden;
    btn.textContent = input.hidden ? "EDIT" : "CANCEL";
    card.querySelector(".title").classList.toggle("editing", !input.hidden);
    if (input.hidden) input.value = input.dataset.orig; else { input.focus(); input.select(); }
  }

  async function review(card, act) {
    const id = card.dataset.id;
    const payload = { note: card.querySelector(".note-input").value };
    const titleInput = card.querySelector(".title-input");
    if (act === "approve" && !titleInput.hidden) {
      const t = titleInput.value.trim();
      if (t && t !== titleInput.dataset.orig) payload.title = t;
    }
    card.querySelectorAll("button").forEach(b => (b.disabled = true));
    try {
      const r = await fetch(`/api/approvals/${id}/${act}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      lastApprovalSig = null;
      await refreshApprovals();
      poll();
    } catch (e) {
      card.querySelector(".err").textContent = "FAILED: " + e.message;
      card.querySelectorAll("button").forEach(b => (b.disabled = false));
    }
  }

  // ------------------------------------------------------------ agent panel
  async function showAgent(id) {
    openAgent = id;
    Station.select(id);
    $("agent-panel").classList.remove("hidden");
    if (lastState) renderRoster(lastState.agents);
    await refreshAgent();
  }
  function hideAgent() {
    openAgent = null;
    Station.select(null);
    $("agent-panel").classList.add("hidden");
    if (lastState) renderRoster(lastState.agents);
  }
  async function refreshAgent() {
    if (!openAgent) return;
    const id = openAgent;
    let data;
    try {
      const r = await fetch(`/api/agents/${encodeURIComponent(id)}`, { cache: "no-store" });
      if (!r.ok) return;
      data = await r.json();
    } catch { return; }
    if (id !== openAgent) return;
    const a = data.agent;
    $("agent-detail").innerHTML = `
      <h3 style="color:${Station.colorOf(a.id)}">${esc(a.name)}</h3>
      <div class="dim">${esc(a.role)}</div>
      <dl>
        <dt>ROOM</dt><dd>${esc(label(a.room))}</dd>
        <dt>STATUS</dt><dd class="st-${esc(a.status)}">${label(a.status)}${a.stale ? ` <span class="dim">(stale heartbeat)</span>` : ""}</dd>
        <dt>TASK</dt><dd>${a.current_task ? esc(a.current_task) : `<span class="empty">none</span>`}</dd>
        <dt>HEARTBEAT</dt><dd>${a.last_heartbeat ? `${ago(a.last_heartbeat)} <span class="dim">(${clock(a.last_heartbeat)})</span>` : "never"}</dd>
      </dl>
      <h2>RECENT EVENTS</h2>
      <ol>${data.events.length ? data.events.map(e => eventItem(e, false)).join("") : `<li class="empty">No events from this agent.</li>`}</ol>`;
  }

  // ------------------------------------------------------------ polling
  let polling = false;
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const s = await r.json();
      lastState = s;
      loadPlugins(s.plugins);
      Station.setAgents(s.agents);
      if (openAgent) Station.select(openAgent);
      renderTop(s);
      renderRoster(s.agents);
      renderEvents(s.events);
      renderPipeline(s);
      $("link-state").textContent = "LINK OK";
      $("link-state").classList.remove("lost");
      refreshApprovals();
      refreshAgent();
      for (const fn of stateHooks) { try { fn(s); } catch (e) { console.error(e); } }
    } catch {
      $("link-state").textContent = "SIGNAL LOST";
      $("link-state").classList.add("lost");
    } finally {
      polling = false;
    }
  }

  function tickClock() {
    $("clock").textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  }

  // ------------------------------------------------------------ wiring
  Station.init($("station"), { onSelect: showAgent });
  $("roster").addEventListener("click", ev => {
    const li = ev.target.closest("li[data-id]");
    if (li) showAgent(li.dataset.id);
  });
  $("agent-close").addEventListener("click", hideAgent);
  document.addEventListener("keydown", ev => { if (ev.key === "Escape") hideAgent(); });
  $("approvals").addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const card = btn.closest(".card");
    if (btn.dataset.act === "edit") toggleEdit(card); else review(card, btn.dataset.act);
  });

  tickClock();
  setInterval(tickClock, 1000);
  poll();
  setInterval(poll, POLL_MS);
})();
