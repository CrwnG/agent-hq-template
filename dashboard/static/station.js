/* Top-down pixel-art space station rendered on a 640x360 canvas.
 * Rooms with hand-drawn props: bridge, observatory, analytics, security, qa_lab,
 * workshop, comms, broadcast, vault. Any other room name gets the generic room.
 * One room per agent on two decks joined by a corridor spine; crew robots walk
 * when working, sit when idle, blink amber when blocked, power down when offline.
 * The layout is computed from the agents present, so a new agent with an
 * unknown room gets a generic room slot instead of disappearing.
 * All art is drawn procedurally here and in sprites.js (original work). */
(function () {
  "use strict";

  const W = 640, H = 360;
  const ROOM_H = 96, TOP_Y = 40, GAP = 10;
  const SPINE = { x: 26, y: TOP_Y + ROOM_H + 18, w: W - 52, h: 18 };
  const BOT_Y = SPINE.y + SPINE.h + 18;
  // Preferred placement: first half of the list is the upper deck (bridge centred).
  const ORDER = ["observatory", "analytics", "bridge", "security", "qa_lab",
                 "workshop", "comms", "broadcast", "vault"];
  let ROOMS = {};            // name -> {x, y, w, h, top}
  let layoutKey = "";
  const SPR_W = 20, SPR_H = 26, SPEED = 16;
  const AMBER = "#ffb52e";
  const WALL = "#26313b", WALL_HI = "#3a4855", FLOOR_A = "#0d1419", FLOOR_B = "#111a20";

  let ctx, canvas, onSelect = () => {};
  let agents = [];            // latest API agents
  const actors = {};          // per-agent animation state
  let selected = null, hovered = null;
  let packets = [];
  let mouse = { x: W / 2, y: H / 2 };
  let plate = "STATION HQ";
  const reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ helpers
  function rng(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function R(x, y, w, h, col) { ctx.fillStyle = col; ctx.fillRect(Math.round(x), Math.round(y), w, h); }
  function disc(cx, cy, r, col) {
    ctx.fillStyle = col;
    for (let dy = -r; dy <= r; dy++) {
      const dx = Math.floor(Math.sqrt(r * r - dy * dy));
      ctx.fillRect(cx - dx, cy + dy, dx * 2 + 1, 1);
    }
  }
  function frame(x, y, w, h, col) { // crisp 1px outline
    ctx.strokeStyle = col; ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, w - 1, h - 1);
  }
  function colorOf(id) { return Pix.cfgFor(id).body; }

  // ------------------------------------------------------------ layout
  function computeLayout(names) {
    const known = ORDER.filter(n => names.includes(n));
    const extra = names.filter(n => !ORDER.includes(n)).sort();
    const all = [...known, ...extra];
    const nTop = Math.ceil(all.length / 2);
    const rooms = {};
    [all.slice(0, nTop), all.slice(nTop)].forEach((row, ri) => {
      if (!row.length) return;
      const avail = W - 68 - GAP * (row.length - 1);
      const w = Math.min(120, Math.floor(avail / row.length));
      let x = Math.round((W - (w * row.length + GAP * (row.length - 1))) / 2);
      for (const name of row) {
        rooms[name] = { x, y: ri === 0 ? TOP_Y : BOT_Y, w, h: ROOM_H, top: ri === 0 };
        x += w + GAP;
      }
    });
    return rooms;
  }
  function syncLayout() {
    const names = [...new Set(agents.map(a => a.room).filter(Boolean))];
    const key = names.slice().sort().join("|");
    if (key !== layoutKey) { layoutKey = key; ROOMS = computeLayout(names); }
  }
  function withAlpha(a, fn) { const p = ctx.globalAlpha; ctx.globalAlpha = a; fn(); ctx.globalAlpha = p; }

  // ------------------------------------------------------------ starfield + planet
  const stars = [];
  (function makeStars() {
    const r = rng(7);
    [[110, 1.2, 0.25], [60, 3.5, 0.6], [24, 8, 1.2]].forEach(([n, speed, depth], layer) => {
      for (let i = 0; i < n; i++) {
        stars.push({
          x: r() * W, y: r() * H, speed, depth, layer,
          phase: r() * Math.PI * 2, tw: 0.8 + r() * 2.5,
          col: r() < 0.15 ? "#bfefff" : r() < 0.3 ? "#caffd6" : "#ffffff",
        });
      }
    });
  })();

  function drawSpace(t) {
    R(0, 0, W, H, "#010306");
    const mx = (mouse.x - W / 2) / W, my = (mouse.y - H / 2) / H;
    for (const s of stars) {
      const drift = reduceMotion ? 0 : t * s.speed;
      const x = ((s.x - drift - mx * 10 * s.depth) % W + W) % W;
      const y = ((s.y - my * 6 * s.depth) % H + H) % H;
      const a = Math.max(0.1, 0.55 + 0.45 * Math.sin(t * s.tw + s.phase)) * (0.45 + s.layer * 0.25);
      withAlpha(a, () => R(x, y, s.layer === 2 ? 2 : 1, s.layer === 2 ? 2 : 1, s.col));
    }
    // distant banded planet, top-right, slowest parallax
    const cx = W - 20 - Math.round(mx * 3), cy = 8 - Math.round(my * 2), pr = 26;
    const bands = ["#1d4a4a", "#245a55", "#1a4048", "#2a6660", "#1d4a4a"];
    for (let dy = -pr; dy <= pr; dy++) {
      const dx = Math.floor(Math.sqrt(pr * pr - dy * dy));
      R(cx - dx, cy + dy, dx * 2 + 1, 1, bands[Math.floor((dy + pr) / 7) % bands.length]);
      const sx = Math.round(dx * 0.25);
      withAlpha(0.5, () => R(cx + sx, cy + dy, dx - sx + 1, 1, "#000"));
    }
  }

  // ------------------------------------------------------------ structure
  function drawStructure(t) {
    // solar arrays + trusses
    const py = SPINE.y + SPINE.h / 2 - 37;
    for (const px of [4, W - 20]) {
      R(px, py, 16, 74, "#1b2a3a");
      for (let yy = py + 2; yy < py + 72; yy += 6) for (let xx = px + 2; xx < px + 14; xx += 6) R(xx, yy, 5, 5, "#24476e");
      withAlpha(0.25 + 0.1 * Math.sin(t * 0.7), () => R(px + 2, py + 2, 12, 1, "#9fd4ff"));
    }
    R(20, SPINE.y + 7, 6, 4, "#56616d"); R(W - 26, SPINE.y + 7, 6, 4, "#56616d");
    // spine corridor
    R(SPINE.x, SPINE.y, SPINE.w, SPINE.h, WALL);
    R(SPINE.x + 2, SPINE.y + 2, SPINE.w - 4, SPINE.h - 4, "#131b22");
    for (let x = SPINE.x + 6; x < SPINE.x + SPINE.w - 4; x += 12) R(x, SPINE.y + 8, 4, 1, "#1d2a33");
    // connectors
    for (const r of Object.values(ROOMS)) {
      const cx = r.x + r.w / 2 - 6;
      const y0 = r.top ? r.y + r.h - 2 : SPINE.y + SPINE.h - 2;
      const y1 = r.top ? SPINE.y + 2 : r.y + 2;
      R(cx, y0, 12, y1 - y0, WALL);
      R(cx + 2, y0, 8, y1 - y0, "#131b22");
    }
    // packets of light travelling the spine
    for (const p of packets) {
      withAlpha(0.35, () => R(p.x - p.dir * 3, SPINE.y + 8, 3, 2, p.col));
      R(p.x, SPINE.y + 8, 2, 2, p.col);
    }
    // name plate
    Pix.drawText(ctx, plate, (W - Pix.textWidth(plate)) / 2, BOT_Y + ROOM_H + 22, "#2a9a48");
  }

  // ------------------------------------------------------------ props (per room)
  const PROPS = {
    bridge(r, on, c, t) {
      R(r.x + 25, r.y + 6, 60, 10, "#3a4855"); R(r.x + 26, r.y + 7, 58, 8, "#06101c");
      for (let i = 0; i < 9; i++) {
        const sx = r.x + 27 + ((i * 13 + (on ? t * 18 : 0)) % 56);
        R(sx, r.y + 8 + (i * 5) % 6, 1, 1, on ? "#d8f4ff" : "#2a3a4a");
      }
      R(r.x + 28, r.y + 24, 54, 7, "#2b3642"); R(r.x + 28, r.y + 24, 54, 1, WALL_HI);
      for (let i = 0; i < 8; i++) {
        const lit = on && Math.sin(t * 4 + i * 1.7) > 0;
        R(r.x + 32 + i * 6, r.y + 27, 3, 1, lit ? c : "#1b3a26");
      }
    },
    observatory(r, on, c, t) {
      const cx = r.x + r.w - 24, cy = r.y + 26;
      disc(cx, cy, 14, WALL_HI); disc(cx, cy, 12, "#040914");
      const rr = rng(3);
      for (let i = 0; i < 14; i++) {
        const a = rr() * Math.PI * 2, d = rr() * 10;
        const tw = on ? 0.5 + 0.5 * Math.sin(t * 3 + i) : 0.3;
        withAlpha(tw, () => R(cx + Math.cos(a) * d, cy + Math.sin(a) * d, 1, 1, "#e8f6ff"));
      }
      withAlpha(0.35, () => disc(cx - 4, cy + 3, 3, "#6a3fa0"));
      // telescope on tripod
      for (let i = 0; i < 10; i++) R(r.x + 16 + i * 2, r.y + 30 - i, 3, 3, "#8a96a3");
      R(r.x + 35, r.y + 20, 2, 2, on && Math.sin(t * 2) > 0.6 ? "#ffffff" : "#5cf2ff");
      R(r.x + 22, r.y + 32, 1, 10, "#56616d"); R(r.x + 18, r.y + 40, 9, 1, "#56616d");
      R(r.x + 12, r.y + 52, 30, 14, "#1d2a36");
      for (let i = 0; i < 6; i++) R(r.x + 15 + i * 4, r.y + 55 + (i * 3) % 8, 1, 1, on ? c : "#2a3a4a");
    },
    security(r, on, c, t) {
      R(r.x + 10, r.y + 24, 90, 4, "#2b3642");
      for (let i = 0; i < 4; i++) {
        const sx = r.x + 10 + i * 23;
        R(sx, r.y + 6, 21, 14, "#3a4855"); R(sx + 1, r.y + 7, 19, 12, "#07160f");
        if (on) {
          withAlpha(0.8, () => R(sx + 1, r.y + 7 + Math.floor((t * 8 + i * 3) % 12), 19, 1, c));
          R(sx + 3 + (i * 5) % 12, r.y + 10 + (i * 2) % 6, 2, 2, "#4dff7a");
        }
      }
      // floor lock plate
      withAlpha(0.35, () => { disc(r.x + 88, r.y + 58, 9, "#26313b"); disc(r.x + 88, r.y + 58, 7, "#0d1419"); });
      R(r.x + 86, r.y + 56, 5, 5, on ? c : "#2a3139");
    },
    workshop(r, on, c, t) {
      // gantry arm over a workbench, assembling a part
      R(r.x + 7, r.y + 6, 52, 24, "#2b3642"); R(r.x + 10, r.y + 9, 46, 18, "#141c22");
      R(r.x + 10, r.y + 12, 46, 1, "#56616d");
      const hx = on ? r.x + 10 + (Math.sin(t * 2.2) * 0.5 + 0.5) * 40 : r.x + 10;
      R(hx, r.y + 10, 6, 4, c);
      if (on) { R(hx + 2, r.y + 14, 2, 1, "#ffffff"); }
      // the part taking shape on the bench
      const sx = r.x + 26, sy = r.y + 17;
      R(sx, sy, 14, 8, on ? "#c8d0d8" : "#555c66"); R(sx + 4, sy - 3, 6, 3, on ? "#8a96a3" : "#3a4048");
      if (on) R(sx + 2, sy + 2, 3, 3, c);
      // output shelf of finished crates
      R(r.x + 64, r.y + 12, 22, 16, "#3a2f22");
      ["#e8504f", "#3fc9f0", "#f2c14a"].forEach((col, i) => R(r.x + 66 + i * 7, r.y + 16, 5, 10, col));
    },
    comms(r, on, c, t) {
      R(r.x + 8, r.y + 12, 16, 16, "#2b3642");
      disc(r.x + 16, r.y + 10, 6, "#8a96a3"); disc(r.x + 16, r.y + 9, 4, "#56616d");
      R(r.x + 16, r.y + 4, 1, 5, "#c8d0d8");
      if (on) {
        for (let k = 0; k < 3; k++) {
          const rad = (t * 10 + k * 7) % 21;
          withAlpha(Math.max(0, 1 - rad / 21) * 0.8, () => {
            ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.beginPath();
            ctx.arc(r.x + 16.5, r.y + 4.5, rad + 2, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
          });
        }
      }
      for (const sx of [r.x + 36, r.x + 62]) {
        R(sx, r.y + 6, 22, 14, "#3a4855"); R(sx + 1, r.y + 7, 20, 12, "#07160f");
        for (let ln = 0; ln < 4; ln++) {
          const w = 4 + ((ln * 7 + (on ? Math.floor(t * 3) : 0) + sx) % 14);
          R(sx + 3, r.y + 9 + ln * 3, w, 1, on ? "#4dff7a" : "#15361f");
        }
      }
      R(r.x + 34, r.y + 22, 52, 4, "#2b3642");
    },
    broadcast(r, on, c, t) {
      const bx = r.x + r.w - 34;
      R(bx, r.y + 5, 28, 9, on ? "#4a0b0b" : "#1d1414");
      Pix.drawText(ctx, "ON AIR", bx + 3, r.y + 7, on ? "#ff4f4f" : "#4a2a2a");
      // light cone
      if (on) {
        withAlpha(0.07, () => {
          ctx.fillStyle = "#fff6c8"; ctx.beginPath();
          ctx.moveTo(r.x + 60, r.y + 15); ctx.lineTo(r.x + 30, r.y + 70); ctx.lineTo(r.x + 80, r.y + 70);
          ctx.closePath(); ctx.fill();
        });
      }
      R(r.x + 60, r.y + 16, 1, 24, "#56616d"); R(r.x + 56, r.y + 11, 9, 5, on ? "#f4ecc0" : "#4a4a44");
      R(r.x + 56, r.y + 40, 9, 1, "#56616d");
      // camera on tripod
      R(r.x + 12, r.y + 20, 13, 8, "#3b4550"); R(r.x + 25, r.y + 22, 4, 4, "#0b0f14");
      R(r.x + 27, r.y + 23, 1, 1, "#9fd4ff");
      R(r.x + 13, r.y + 21, 2, 1, on && Math.sin(t * 5) > -0.3 ? "#ff3333" : "#442222");
      R(r.x + 18, r.y + 28, 1, 12, "#56616d"); R(r.x + 13, r.y + 40, 11, 1, "#56616d");
    },
    vault(r, on, c, t) {
      const cx = r.x + 22, cy = r.y + 26;
      disc(cx, cy, 15, "#56616d"); disc(cx, cy, 13, "#3a434d"); disc(cx, cy, 10, "#2a3139");
      const a0 = on ? t * 0.9 : 0.4;
      for (let k = 0; k < 3; k++) {
        const a = a0 + (k * Math.PI * 2) / 3;
        for (let i = 3; i < 10; i++) R(cx + Math.cos(a) * i, cy + Math.sin(a) * i, 1, 1, "#9aa6b2");
      }
      disc(cx, cy, 2, on ? c : "#8a96a3");
      for (let i = 0; i < 4; i++) {
        R(r.x + 44 + i * 11, r.y + 6, 10, 22, "#28313a"); R(r.x + 44 + i * 11, r.y + 6, 10, 1, WALL_HI);
        R(r.x + 51 + i * 11, r.y + 15, 1, 3, "#8a96a3");
      }
      R(r.x + 44, r.y + 31, 43, 7, "#07140c");
      if (on) for (let i = 0; i < 6; i++) {
        const bx = r.x + 45 + ((i * 9 + t * 14) % 40);
        R(bx, r.y + 33 + (i % 2) * 2, 4, 1, c);
      }
    },
    analytics(r, on, c, t) {
      // wall of three chart screens: bars, trace, ring (decorative, no figures)
      const sw = Math.floor((r.w - 24) / 3), tt = on ? t : 0;
      const dimC = "#1f3a5a";
      for (let i = 0; i < 3; i++) {
        const sx = r.x + 8 + i * (sw + 4), sy = r.y + 6;
        R(sx, sy, sw, 18, "#3a4855"); R(sx + 1, sy + 1, sw - 2, 16, "#060d18");
        if (i === 0) {
          for (let b = 0; b < 5; b++) {
            const hgt = 3 + Math.round((Math.sin(tt * 1.5 + b * 1.3) * 0.5 + 0.5) * 9);
            R(sx + 3 + b * Math.floor((sw - 6) / 5), sy + 15 - hgt, 3, hgt, on ? c : dimC);
          }
        } else if (i === 1) {
          for (let px = 2; px < sw - 2; px++) {
            const yv = 9 + Math.sin((px + tt * 8) * 0.45) * 3 + Math.sin(px * 0.21) * 2;
            R(sx + px, sy + Math.round(yv), 1, 1, on ? "#9fd4ff" : dimC);
          }
        } else {
          const cx = sx + Math.floor(sw / 2), cy = sy + 9, rad = 6;
          const sweep = on ? (tt * 0.8) % (Math.PI * 2) : 1.6;
          for (let dy = -rad; dy <= rad; dy++) for (let dx = -rad; dx <= rad; dx++) {
            if (dx * dx + dy * dy > rad * rad) continue;
            let a = Math.atan2(dy, dx); if (a < 0) a += Math.PI * 2;
            R(cx + dx, cy + dy, 1, 1, a < sweep ? (on ? c : dimC) : "#15233a");
          }
        }
      }
      // holo table with light columns
      const tx = r.x + r.w / 2 - 20;
      R(tx, r.y + 38, 40, 9, "#1d2a36"); R(tx, r.y + 38, 40, 1, WALL_HI);
      if (on) for (let k = 0; k < 5; k++) {
        const hgt = 4 + Math.round((Math.sin(t * 2 + k) * 0.5 + 0.5) * 10);
        withAlpha(0.45, () => R(tx + 5 + k * 7, r.y + 37 - hgt, 3, hgt, c));
      }
    },
    qa_lab(r, on, c, t) {
      // scanner gantry over an inspection bench
      const bw = r.w - 44, bx = r.x + 8;
      R(bx, r.y + 6, 2, 22, "#56616d"); R(bx + bw - 2, r.y + 6, 2, 22, "#56616d");
      R(bx, r.y + 6, bw, 2, "#8a96a3");
      R(bx - 1, r.y + 28, bw + 2, 8, "#2b3642"); R(bx - 1, r.y + 28, bw + 2, 1, WALL_HI);
      // sample under inspection on the bench
      const sx = bx + Math.floor(bw / 2) - 7;
      R(sx, r.y + 19, 14, 9, "#dfe6ec"); R(sx + 2, r.y + 21, 10, 1, "#8a96a3"); R(sx + 2, r.y + 24, 7, 1, "#8a96a3");
      const hx = on ? bx + 3 + (Math.sin(t * 1.6) * 0.5 + 0.5) * (bw - 10) : bx + 3;
      R(hx, r.y + 8, 5, 3, "#c8d0d8");
      if (on) {
        withAlpha(0.75, () => R(hx + 2, r.y + 11, 1, 17, c));
        withAlpha(0.5, () => R(hx, r.y + 27, 5, 1, c));
      }
      // pass / hold indicator panel
      const px = r.x + r.w - 30;
      R(px, r.y + 6, 22, 20, "#1a2229"); R(px, r.y + 6, 22, 1, WALL_HI);
      const phase = Math.floor(t * 1.3) % 3;
      disc(px + 6, r.y + 16, 3, on && phase < 2 ? "#4dff7a" : "#173a22");
      disc(px + 15, r.y + 16, 3, on && phase === 2 ? "#ff4f4f" : "#3a1717");
      // swatch rack
      R(px, r.y + 32, 22, 14, "#28313a");
      ["#e8504f", "#3fc9f0", "#f2c14a", "#a878f2"].forEach((col, i) => R(px + 2 + i * 5, r.y + 35, 3, 8, col));
    },
    generic(r, on, c, t) {
      R(r.x + 8, r.y + 6, 24, 16, "#3a4855"); R(r.x + 9, r.y + 7, 22, 14, "#07160f");
      if (on) for (let ln = 0; ln < 3; ln++) R(r.x + 11, r.y + 9 + ln * 4, 6 + ((ln * 5 + Math.floor(t * 2)) % 12), 1, c);
      if (Math.floor(t * 2) % 2) R(r.x + 27, r.y + 17, 2, 2, on ? "#b8ffcb" : "#15361f");
      for (const [dx, dy] of [[r.w - 26, 8], [r.w - 26, 24], [r.w - 44, 24]]) {
        if (dx < 34) continue;
        R(r.x + dx, r.y + dy, 16, 14, "#3a2f22"); R(r.x + dx, r.y + dy, 16, 1, "#5a4a36");
        R(r.x + dx + 7, r.y + dy + 1, 2, 13, "#2a2118");
      }
    },
  };

  // ------------------------------------------------------------ rooms
  function drawRoom(name, r, agent, t, extra = 0) {
    const st = agent ? agent.status : "offline";
    const c = agent ? colorOf(agent.id) : "#667";
    const on = st === "working";
    const blinkOn = Math.floor(t * 2) % 2 === 0;

    if (on) { // outer glow
      const pulse = 0.75 + 0.25 * Math.sin(t * 3);
      for (let k = 1; k <= 3; k++) withAlpha((0.42 - k * 0.12) * pulse, () => frame(r.x - k, r.y - k, r.w + 2 * k, r.h + 2 * k, c));
    } else if (st === "blocked" && blinkOn) {
      for (let k = 1; k <= 2; k++) withAlpha(0.45 - k * 0.15, () => frame(r.x - k, r.y - k, r.w + 2 * k, r.h + 2 * k, AMBER));
    }

    R(r.x, r.y, r.w, r.h, WALL);
    R(r.x, r.y, r.w, 1, WALL_HI);
    for (let y = r.y + 3; y < r.y + r.h - 3; y += 8) {
      for (let x = r.x + 3; x < r.x + r.w - 3; x += 8) {
        R(x, y, Math.min(8, r.x + r.w - 3 - x), Math.min(8, r.y + r.h - 3 - y),
          ((x - r.x - 3) / 8 + (y - r.y - 3) / 8) % 2 ? FLOOR_A : FLOOR_B);
      }
    }
    // doorway toward the spine
    const dx = r.x + r.w / 2 - 4;
    R(dx, r.top ? r.y + r.h - 3 : r.y, 8, 3, "#131b22");

    ctx.save(); // props never bleed outside a (possibly narrow) room
    ctx.beginPath(); ctx.rect(r.x + 3, r.y + 3, r.w - 6, r.h - 6); ctx.clip();
    (PROPS[name] || PROPS.generic)(r, on, c, t);
    ctx.restore();

    // lighting by status
    let strip = "#1a1f24";
    if (on) { withAlpha(0.07 + 0.03 * Math.sin(t * 3), () => R(r.x + 3, r.y + 3, r.w - 6, r.h - 6, c)); strip = c; }
    else if (st === "idle") { withAlpha(0.38, () => R(r.x + 3, r.y + 3, r.w - 6, r.h - 6, "#000")); strip = "#2a4a36"; }
    else if (st === "blocked") {
      withAlpha(0.25, () => R(r.x + 3, r.y + 3, r.w - 6, r.h - 6, "#000"));
      if (blinkOn) withAlpha(0.12, () => R(r.x + 3, r.y + 3, r.w - 6, r.h - 6, AMBER));
      strip = blinkOn ? AMBER : "#5a3f10";
    } else { withAlpha(0.74, () => R(r.x + 3, r.y + 3, r.w - 6, r.h - 6, "#000")); }
    frame(r.x + 2, r.y + 2, r.w - 4, r.h - 4, strip);

    // label outside the room: ROOM  NAME  + status LED
    const ly = r.top ? r.y - 8 : r.y + r.h + 3;
    const maxC = Math.floor((r.w - 8) / 4);
    let roomTxt = name.replace(/_/g, " ").toUpperCase();
    let nameTxt = agent ? String(agent.name || agent.id).toUpperCase() + (extra ? "+" + extra : "") : "";
    if (roomTxt.length + 1 + nameTxt.length > maxC) {
      nameTxt = nameTxt.slice(0, Math.max(0, maxC - roomTxt.length - 1));
      if (!nameTxt) roomTxt = roomTxt.slice(0, maxC);
    }
    Pix.drawText(ctx, roomTxt, r.x + 1, ly, st === "offline" ? "#2d3a33" : "#2a9a48");
    if (nameTxt) {
      const nx = r.x + 1 + Pix.textWidth(roomTxt) + 5;
      Pix.drawText(ctx, nameTxt, nx, ly, st === "offline" ? "#3a4048" : c);
    }
    const led = on ? c : st === "blocked" ? (blinkOn ? AMBER : "#5a3f10") : st === "idle" ? "#2a6a40" : "#222a30";
    R(r.x + r.w - 5, ly, 4, 4, "#0b0f14"); R(r.x + r.w - 4, ly + 1, 2, 2, led);

    if (name === selected || name === hovered) brackets(r, name === selected ? "#b8ffcb" : "#2a9a48");
  }

  function brackets(r, col) {
    const x0 = r.x - 4, y0 = r.y - 4, x1 = r.x + r.w + 3, y1 = r.y + r.h + 3, L = 7;
    R(x0, y0, L, 1, col); R(x0, y0, 1, L, col);
    R(x1 - L + 1, y0, L, 1, col); R(x1, y0, 1, L, col);
    R(x0, y1, L, 1, col); R(x0, y1 - L + 1, 1, L, col);
    R(x1 - L + 1, y1, L, 1, col); R(x1, y1 - L + 1, 1, L, col);
  }

  // ------------------------------------------------------------ actors
  // Seat: bottom-centre of the room; room-mates sit side by side.
  function seatOf(r, slot = 0) {
    const off = slot === 0 ? 0 : (slot % 2 ? -1 : 1) * Math.ceil(slot / 2) * (SPR_W + 4);
    const x = r.x + r.w / 2 - SPR_W / 2 + off;
    return { x: Math.max(r.x + 4, Math.min(r.x + r.w - 4 - SPR_W, x)), y: r.y + r.h - 38 };
  }
  function pickTarget(a, r) {
    a.tx = r.x + 6 + Math.random() * (r.w - 12 - SPR_W);
    a.ty = r.y + 14 + Math.random() * (r.h - 19 - SPR_H);
  }
  function actorFor(agent, r, slot) {
    let a = actors[agent.id];
    const key = `${r.x},${r.y},${r.w},${slot}`;
    if (!a || a.key !== key) { // new agent, or the layout moved its room: re-seat
      const s = seatOf(r, slot);
      a = actors[agent.id] = { key, x: s.x, y: s.y, tx: s.x, ty: s.y, pause: Math.random(), moving: false,
        nextBlink: 1 + Math.random() * 4, blinkUntil: 0, nextPacket: Math.random() * 2 };
    }
    return a;
  }

  function stepActor(agent, r, dt, t, slot) {
    const a = actorFor(agent, r, slot);
    const st = agent.status;
    let tx, ty;
    if (st === "working") {
      if (a.pause > 0) { a.pause -= dt; a.moving = false; return a; }
      tx = a.tx; ty = a.ty;
    } else { const s = seatOf(r, slot); tx = s.x; ty = s.y; }
    const dx = tx - a.x, dy = ty - a.y, d = Math.hypot(dx, dy);
    if (d < 0.8) {
      a.x = tx; a.y = ty; a.moving = false;
      if (st === "working") { a.pause = 0.6 + Math.random() * 2; pickTarget(a, r); }
    } else {
      const s = Math.min(d, SPEED * (st === "working" ? 1 : 1.4) * dt);
      a.x += (dx / d) * s; a.y += (dy / d) * s; a.moving = true;
    }
    if (t > a.nextBlink) { a.blinkUntil = t + 0.14; a.nextBlink = t + 2 + Math.random() * 4; }
    if (st === "working" && t > a.nextPacket) {
      a.nextPacket = t + 1.5 + Math.random() * 2;
      const hub = ROOMS.bridge ? ROOMS.bridge.x + ROOMS.bridge.w / 2 : W / 2;
      const from = r.x + r.w / 2;
      const to = agent.room === "bridge" ? SPINE.x + 14 + Math.random() * (SPINE.w - 28) : hub;
      if (Math.abs(to - from) > 8) packets.push({ x: from, to, dir: Math.sign(to - from), col: colorOf(agent.id) });
    }
    return a;
  }

  function drawActor(agent, r, a, t) {
    const st = agent.status;
    const x = Math.round(a.x), y = Math.round(a.y);
    const blink = t < a.blinkUntil;
    const sitting = !a.moving && (st === "idle" || st === "offline");
    if (sitting) { // chair
      R(x - 1, y + 12, SPR_W + 2, 12, "#2f3943"); R(x - 1, y + 12, SPR_W + 2, 1, "#46535f");
    }
    withAlpha(0.45, () => R(x + 3, y + SPR_H - 1, SPR_W - 6, 2, "#000"));
    let pose = "stand", bob = 0;
    if (a.moving) { const f = Math.floor(t * 6) % 2; pose = f ? "stepA" : "stepB"; bob = f; }
    else if (sitting) { pose = "sit"; bob = 2; }
    const spr = Pix.robot(agent.id, pose, st !== "offline", blink);
    ctx.drawImage(spr, 0, 0, 10, 13, x, y + bob, SPR_W, SPR_H);

    if (st === "working" && !a.moving && Math.sin(t * 9) > 0.3) R(x + SPR_W, y + 16, 1, 1, "#ffffff"); // tool spark
    if (st === "blocked" && Math.floor(t * 2) % 2 === 0) Pix.drawText(ctx, "!", x + 9, y - 8, AMBER);
    if (st === "idle") {
      const p = (t * 0.5 + x * 0.01) % 1;
      withAlpha(0.6 * (1 - p), () => Pix.drawText(ctx, "Z", x + 15 + p * 4, y - 2 - p * 8, "#6aa982"));
    }
  }

  // ------------------------------------------------------------ loop
  let last = 0;
  function tick(ms) {
    const t = ms / 1000, dt = Math.min(0.1, last ? t - last : 0);
    last = t;
    syncLayout();
    const byRoom = {};
    for (const ag of agents) if (ROOMS[ag.room]) (byRoom[ag.room] = byRoom[ag.room] || []).push(ag);
    const RANK = { working: 3, blocked: 2, idle: 1, offline: 0 };

    packets = packets.filter(p => {
      p.x += p.dir * 40 * dt;
      return p.dir > 0 ? p.x < p.to : p.x > p.to;
    });

    drawSpace(t);
    drawStructure(t);
    for (const [name, r] of Object.entries(ROOMS)) {
      const crew = byRoom[name] || [];
      // the room shows its most active occupant's state
      const lead = crew.slice().sort((a, b) => (RANK[b.status] || 0) - (RANK[a.status] || 0))[0];
      drawRoom(name, r, lead, t, Math.max(0, crew.length - 1));
      crew.forEach((ag, i) => drawActor(ag, r, stepActor(ag, r, dt, t, i), t));
    }
    requestAnimationFrame(tick);
  }

  // ------------------------------------------------------------ input
  function toLogical(ev) {
    const b = canvas.getBoundingClientRect();
    const s = Math.min(b.width / W, b.height / H);
    const ox = (b.width - W * s) / 2, oy = (b.height - H * s) / 2;
    return { x: (ev.clientX - b.left - ox) / s, y: (ev.clientY - b.top - oy) / s };
  }
  function roomAt(p) {
    for (const [name, r] of Object.entries(ROOMS)) {
      if (p.x >= r.x - 3 && p.x <= r.x + r.w + 3 && p.y >= r.y - 10 && p.y <= r.y + r.h + 10) return name;
    }
    return null;
  }

  function init(el, opts = {}) {
    canvas = el; ctx = el.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    onSelect = opts.onSelect || onSelect;
    el.addEventListener("mousemove", ev => {
      const p = toLogical(ev); mouse = p;
      hovered = roomAt(p); el.style.cursor = hovered ? "pointer" : "default";
    });
    el.addEventListener("mouseleave", () => { hovered = null; mouse = { x: W / 2, y: H / 2 }; });
    el.addEventListener("click", ev => {
      const room = roomAt(toLogical(ev));
      const ag = room && agents.find(a => a.room === room);
      if (ag) onSelect(ag.id);
    });
    requestAnimationFrame(tick);
  }

  function setAgents(list) { agents = Array.isArray(list) ? list : []; }
  // Name plate under the station; the 3x5 font has A-Z, 0-9 and a few symbols.
  function setTitle(name) {
    const txt = String(name || "").toUpperCase().replace(/[^A-Z0-9 \-.:\/!?#%$+<>_']/g, " ").trim().slice(0, 40);
    plate = txt ? "STATION " + txt : "STATION HQ";
  }
  function select(agentId) {
    const ag = agents.find(a => a.id === agentId);
    selected = ag ? ag.room : null;
  }

  window.Station = { init, setAgents, select, colorOf, setTitle };
})();
