/* Procedural pixel art: a 3x5 bitmap font and the crew robot sprites.
 * All art is original and generated from the small pixel maps below. */
(function () {
  "use strict";

  // ------------------------------------------------------------ 3x5 font
  const GLYPHS = {
    A: "010101111101101", B: "110101110101110", C: "011100100100011", D: "110101101101110",
    E: "111100110100111", F: "111100110100100", G: "011100101101011", H: "101101111101101",
    I: "111010010010111", J: "001001001101010", K: "101101110101101", L: "100100100100111",
    M: "101111111101101", N: "110101101101101", O: "010101101101010", P: "110101110100100",
    Q: "010101101110011", R: "110101110101101", S: "011100010001110", T: "111010010010010",
    U: "101101101101111", V: "101101101101010", W: "101101111111101", X: "101101010101101",
    Y: "101101010010010", Z: "111001010100111",
    0: "111101101101111", 1: "010110010010111", 2: "110001010100111", 3: "110001010001110",
    4: "101101111001001", 5: "111100110001110", 6: "011100111101111", 7: "111001010010010",
    8: "111101111101111", 9: "111101111001110",
    " ": "000000000000000", "-": "000000111000000", ".": "000000000000010", ":": "000010000010000",
    "/": "001001010100100", "!": "010010010000010", "?": "110001010000010", "#": "101111101111101",
    "%": "101001010100101", "$": "011110010011110", "+": "000010111010000", ">": "100010001010100",
    "<": "001010100010001", "_": "000000000000111", "'": "010010000000000",
  };

  function textWidth(text, scale = 1) {
    return text.length ? (text.length * 4 - 1) * scale : 0;
  }

  function drawText(ctx, text, x, y, color, scale = 1) {
    ctx.fillStyle = color;
    let cx = Math.round(x);
    for (const ch of String(text).toUpperCase()) {
      const g = GLYPHS[ch] || GLYPHS["?"];
      for (let i = 0; i < 15; i++) {
        if (g[i] === "1") ctx.fillRect(cx + (i % 3) * scale, Math.round(y) + ((i / 3) | 0) * scale, scale, scale);
      }
      cx += 4 * scale;
    }
  }

  // ------------------------------------------------------------ robots
  // 10 x 13 pixel map. o=outline b=body h=highlight e=eye a=accent l=leg p=panel
  const BODY = [
    "..........",
    "..........",
    "..oooooo..",
    ".obhhhhbo.",
    ".obebbebo.",
    ".obbbbbbo.",
    "..oooooo..",
    "..obppbo..",
    ".aobbbboa.",
    ".aobbbboa.",
    "..oooooo..",
    "..........",
    "..........",
  ];
  const TOPS = {
    mast:  ["....aa....", "....oo...."],
    twin:  ["..a....a..", "..o....o.."],
    crest: ["...aaaa...", "..oaaaao.."],
    dome:  ["..........", "...oooo..."],
    ears:  ["..........", "..........", null, "aobhhhhboa", "aobebbeboa"],
    tri:   ["..a.aa.a..", "..o.oo.o.."],
    band:  ["..........", "..aaaaaa.."],
  };
  const EYES = {
    pair:  ".obebbebo.",
    visor: ".obeeeebo.",
    mono:  ".obbeebbo.",
    wide:  ".oebbbbeo.",
    quad:  ".oebeebeo.",
  };
  const LEGS = {
    stand: ["...l..l...", "..ll..ll.."],
    stepA: ["..l....l..", ".ll.....l."],
    stepB: ["...l..l...", "...ll.ll.."],
    sit:   ["..llllll..", ".........."],
  };

  // Distinct colour + silhouette per crew member.
  // Hand-picked looks for the starter crew; add yours here, or let cfgFor() derive one.
  const CREW = {
    architect:  { body: "#f2c14a", accent: "#fff3b0", eye: "#ffffff", top: "crest", eyes: "visor" },
    critic:     { body: "#c6f24e", accent: "#f2ffc8", eye: "#ff5c5c", top: "band",  eyes: "mono" },
    researcher: { body: "#3fc9f0", accent: "#c8f6ff", eye: "#fff7a8", top: "mast",  eyes: "mono" },
    builder:    { body: "#f08a2e", accent: "#ffd29a", eye: "#fffbe0", top: "dome",  eyes: "pair" },
  };
  const FALLBACK = { body: "#9aa3ad", accent: "#e0e6ea", eye: "#ffffff", top: "mast", eyes: "pair" };

  // Future agents without a hand-picked look get a stable one derived from their id.
  function hslHex(h, s, l) {
    const f = n => {
      const k = (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
      return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))).toString(16).padStart(2, "0");
    };
    return "#" + f(0) + f(8) + f(4);
  }
  function cfgFor(id) {
    if (CREW[id]) return CREW[id];
    if (!id) return FALLBACK;
    let hsh = 2166136261;
    for (const ch of String(id)) hsh = Math.imul(hsh ^ ch.charCodeAt(0), 16777619) >>> 0;
    const tops = Object.keys(TOPS), eyes = Object.keys(EYES);
    const cfg = {
      body: hslHex(hsh % 360, 0.6, 0.6), accent: hslHex(hsh % 360, 0.7, 0.85), eye: "#ffffff",
      top: tops[(hsh >>> 9) % tops.length], eyes: eyes[(hsh >>> 17) % eyes.length],
    };
    CREW[id] = cfg;
    return cfg;
  }

  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v =>
      Math.max(0, Math.min(255, Math.round(f >= 0 ? v + (255 - v) * f : v * (1 + f)))));
    return "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
  }
  function grey(hex) {
    const n = parseInt(hex.slice(1), 16);
    const g = Math.round(((n >> 16) & 255) * .3 + ((n >> 8) & 255) * .59 + (n & 255) * .11) * 0.45;
    const v = Math.round(g).toString(16).padStart(2, "0");
    return "#" + v + v + v;
  }

  function buildMap(cfg, legs) {
    const rows = BODY.slice();
    const top = TOPS[cfg.top] || TOPS.mast;
    top.forEach((r, i) => { if (r) rows[i] = r; });
    if (cfg.top !== "ears") rows[4] = EYES[cfg.eyes] || EYES.pair;
    else rows[4] = rows[4].slice(0, 2) + EYES[cfg.eyes].slice(2, 8) + rows[4].slice(8);
    rows[11] = LEGS[legs][0];
    rows[12] = LEGS[legs][1];
    return rows;
  }

  const cache = new Map();

  /** Returns an offscreen canvas (10x13) for an agent in a pose.
   *  pose: stand | stepA | stepB | sit ; powered=false renders a dark, switched-off unit. */
  function robot(agentId, pose = "stand", powered = true, blink = false) {
    const key = `${agentId}|${pose}|${powered}|${blink}`;
    if (cache.has(key)) return cache.get(key);
    const cfg = cfgFor(agentId);
    const body = powered ? cfg.body : grey(cfg.body);
    const pal = {
      o: "#0b0f14",
      b: body,
      h: shade(body, 0.35),
      p: powered ? shade(body, -0.35) : "#222",
      a: powered ? cfg.accent : grey(cfg.accent),
      e: !powered ? "#111" : blink ? shade(body, -0.2) : cfg.eye,
      l: powered ? "#59616c" : "#2c3036",
    };
    const map = buildMap(cfg, pose);
    const c = document.createElement("canvas");
    c.width = 10; c.height = 13;
    const g = c.getContext("2d");
    map.forEach((row, y) => {
      for (let x = 0; x < 10; x++) {
        const col = pal[row[x]];
        if (col) { g.fillStyle = col; g.fillRect(x, y, 1, 1); }
      }
    });
    cache.set(key, c);
    return c;
  }

  window.Pix = { drawText, textWidth, robot, shade, cfgFor, CREW, FALLBACK };
})();
