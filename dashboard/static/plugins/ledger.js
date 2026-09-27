/* Ledger plugin: money stats in the top bar, the monthly goal ladder (when
 * HQ_GOAL_CENTS is set), and a MONEY modal with the month's P&L per platform,
 * a manual entry form and the last 20 entries.
 * Every number comes from /api/ledger*; nothing is estimated client-side. */
(function () {
  "use strict";
  if (!window.HQ) return;
  const { esc, money, label } = HQ.util;
  const $ = id => document.getElementById(id);
  const cell = c => `<td class="${c < 0 ? "neg" : c > 0 ? "pos" : ""}">${money(c)}</td>`;
  const thisMonth = () => new Date().toISOString().slice(0, 7);
  let month = thisMonth();

  // ------------------------------------------------------------ DOM
  HQ.slots.topbar.insertAdjacentHTML("beforeend", `
    <div class="stat"><span class="lbl">REVENUE</span><span class="val" id="m-revenue">$0.00</span></div>
    <div class="stat"><span class="lbl">PROFIT</span><span class="val" id="m-profit">$0.00</span></div>
    <div class="stat"><span class="lbl">INVESTED</span><span class="val" id="m-invested">$0.00</span></div>
    <button class="money-btn" id="money-open" title="P&amp;L, record money, recent entries">$ MONEY</button>`);
  HQ.slots.banner.insertAdjacentHTML("beforeend", `
    <section class="goals hidden" id="goals">
      <div class="goals-title">MONTHLY PROFIT <span id="goal-month" class="dim"></span> <span id="goal-profit"></span></div>
      <div class="goal-bars" id="goal-bars"></div>
    </section>`);
  document.body.insertAdjacentHTML("beforeend", `
    <div class="modal hidden" id="money-modal" role="dialog" aria-modal="true" aria-labelledby="money-title">
      <div class="modal-box panel">
        <button class="close" id="money-close" aria-label="Close">&times;</button>
        <h2 id="money-title">MONEY // LEDGER
          <label class="dim">MONTH <input type="month" id="money-month" aria-label="Month"></label>
        </h2>
        <div class="money-grid">
          <section>
            <h3>P&amp;L BY PLATFORM</h3>
            <div class="tbl-wrap"><table class="mtable" id="money-pnl"></table></div>
            <div id="money-goal" class="money-goal"></div>
          </section>
          <section>
            <h3>RECORD MONEY <span class="dim">(real transactions only)</span></h3>
            <form id="money-form" autocomplete="off">
              <div class="frow">
                <label>TYPE<select name="kind" required>
                  <option value="sale">SALE (+)</option>
                  <option value="cost">COST (&minus;)</option>
                  <option value="fee">FEE (&minus;)</option>
                  <option value="refund">REFUND (&minus;)</option>
                  <option value="investment">INVESTMENT (&minus;)</option>
                  <option value="payout">PAYOUT (bank, not profit)</option>
                </select></label>
                <label>AMOUNT $<input name="amount" id="mf-amount" inputmode="decimal" placeholder="25.00" required maxlength="12"></label>
              </div>
              <div class="frow">
                <label>PLATFORM<input name="platform" placeholder="stripe / cash / other" required maxlength="32"></label>
                <label>DATE<input name="date" id="mf-date" type="date"></label>
              </div>
              <label>REF <span class="dim">(invoice / order #, stops duplicates)</span><input name="ref" maxlength="120"></label>
              <label>NOTE<input name="note" maxlength="500" placeholder="what was it?"></label>
              <div class="frow"><button type="submit" class="btn-approve" id="mf-submit">RECORD</button>
                <span class="hint dim">Type the amount as positive; the sign follows the type.</span></div>
              <div class="err lv-error" id="money-err" role="alert"></div>
              <div class="ok lv-success" id="money-ok" role="status"></div>
            </form>
          </section>
        </div>
        <h3>LAST 20 ENTRIES</h3>
        <div class="tbl-wrap"><table class="mtable" id="money-recent"></table></div>
      </div>
    </div>`);
  const modal = $("money-modal");

  // ------------------------------------------------------------ top bar + goals
  async function refreshSummary() {
    let m;
    try { m = await (await fetch("/api/ledger/summary", { cache: "no-store" })).json(); } catch { return; }
    const set = (id, cents) => { const el = $(id); el.textContent = money(cents); el.classList.toggle("neg", cents < 0); };
    set("m-revenue", m.revenue_cents);
    set("m-profit", m.profit_cents);
    set("m-invested", m.invested_cents);
    const goals = m.goals_cents || [];
    $("goals").classList.toggle("hidden", !goals.length);
    if (!goals.length) return;
    const mp = m.month_profit_cents || 0;
    $("goal-month").textContent = m.month ? `[${m.month}]` : "";
    $("goal-profit").textContent = money(mp);
    $("goal-bars").innerHTML = goals.map((g, i) => {
      const pct = g > 0 ? Math.max(0, Math.min(100, (mp / g) * 100)) : 0;
      const done = mp >= g;
      return `<div class="goal">
        <div class="meta"><span class="${done ? "done" : ""}">${g === m.goal_cents ? "GOAL" : i === 0 ? "REACHED" : "NEXT"} ${done ? "&#10003;" : ""}</span>
        <span>${money(Math.max(0, mp))} / ${money(g)} &middot; ${pct.toFixed(0)}%</span></div>
        <div class="bar" role="progressbar" aria-valuenow="${pct.toFixed(0)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct}%"></i></div>
      </div>`;
    }).join("");
  }
  let tick = 0;
  HQ.onState(() => { if (tick++ % 5 === 0) refreshSummary(); });  // every ~10 s

  // ------------------------------------------------------------ modal
  function renderPnl(p) {
    const head = `<tr><th>PLATFORM</th><th>REVENUE</th><th>REFUNDS</th><th>FEES</th><th>COSTS</th><th>NET</th></tr>`;
    const rows = p.platforms.filter(x => x.entries).map(x =>
      `<tr><td>${esc(label(x.platform))}</td>${cell(x.revenue)}${cell(x.refunds)}${cell(x.fees)}${cell(x.costs)}${cell(x.net)}</tr>`);
    const t = p.totals;
    if (!rows.length) rows.push(`<tr><td colspan="6" class="empty">No ledger entries for ${esc(p.month)} &mdash; nothing is estimated.</td></tr>`);
    rows.push(`<tr class="total"><td>TOTAL</td>${cell(t.revenue)}${cell(t.refunds)}${cell(t.fees)}${cell(t.costs)}${cell(t.net)}</tr>`);
    $("money-pnl").innerHTML = head + rows.join("");
    const extra = (t.investment || t.payout)
      ? `<div class="dim">Invested ${money(-t.investment)} &middot; paid out to bank ${money(t.payout)} (not in net)</div>` : "";
    const goal = p.goal_cents
      ? (p.goal_met ? `<div class="lv-success">${money(p.goal_cents)} goal reached.</div>`
        : `<div class="dim">${money(p.to_goal_cents)} more net profit to the ${money(p.goal_cents)} goal.</div>`)
      : `<div class="dim">No monthly goal set (HQ_GOAL_CENTS in .env).</div>`;
    $("money-goal").innerHTML = `<div>NET ${esc(p.month)}: <b class="${t.net < 0 ? "neg" : ""}">${money(t.net)}</b></div>${goal}${extra}`;
  }

  function renderRecent(rows) {
    const head = `<tr><th>#</th><th>DATE</th><th>PLATFORM</th><th>KIND</th><th>AMOUNT</th><th>REF / NOTE</th></tr>`;
    $("money-recent").innerHTML = head + (rows.length ? rows.map(r => `<tr>
      <td>${r.id}</td><td>${esc(String(r.ts || "").slice(0, 10))}</td><td>${esc(label(r.platform || "-"))}</td>
      <td>${esc(label(r.kind))}</td>${cell(r.amount_cents)}
      <td class="txt">${esc(r.ref || "")}${r.ref && r.note ? " &middot; " : ""}${esc(r.note || "")}</td></tr>`).join("")
      : `<tr><td colspan="6" class="empty">Ledger is empty.</td></tr>`);
  }

  async function refresh() {
    try {
      const l = await (await fetch(`/api/ledger?month=${encodeURIComponent(month)}`, { cache: "no-store" })).json();
      renderPnl(l.pnl);
      renderRecent(l.recent || []);
    } catch (e) {
      $("money-err").textContent = "LOAD FAILED: " + e.message;
    }
  }

  function open() {
    modal.classList.remove("hidden");
    $("money-month").value = month;
    if (!$("mf-date").value) {
      const d = new Date();
      $("mf-date").value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    }
    refresh();
    $("mf-amount").focus();
  }
  function close() { modal.classList.add("hidden"); }

  async function submit(ev) {
    ev.preventDefault();
    const f = ev.target;
    $("money-err").textContent = ""; $("money-ok").textContent = "";
    const body = {
      kind: f.kind.value, amount: f.amount.value.trim(), platform: f.platform.value.trim(),
      ref: f.ref.value.trim() || null, note: f.note.value.trim() || null, date: f.date.value || null,
    };
    $("mf-submit").disabled = true;
    try {
      const r = await fetch("/api/ledger", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const d = data.detail;
        throw new Error(Array.isArray(d) ? d.map(x => `${(x.loc || []).slice(-1)[0]}: ${x.msg}`).join("; ") : (d || r.statusText));
      }
      const e = data.entry;
      $("money-ok").textContent = `RECORDED #${e.id}: ${label(e.kind)} ${money(e.amount_cents)} (${e.platform})`;
      f.amount.value = ""; f.ref.value = ""; f.note.value = "";
      month = e.ts.slice(0, 7);
      $("money-month").value = month;
      refresh();
      refreshSummary();
    } catch (e) {
      $("money-err").textContent = "REFUSED: " + e.message;
    } finally {
      $("mf-submit").disabled = false;
    }
  }

  $("money-open").addEventListener("click", open);
  $("money-close").addEventListener("click", close);
  modal.addEventListener("click", ev => { if (ev.target === modal) close(); });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !modal.classList.contains("hidden")) close(); });
  $("money-month").addEventListener("change", ev => { if (/^\d{4}-\d{2}$/.test(ev.target.value)) { month = ev.target.value; refresh(); } });
  $("money-form").addEventListener("submit", submit);
})();
