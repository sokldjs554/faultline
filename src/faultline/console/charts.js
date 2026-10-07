/* 차트 프리미티브 — 의존성 없는 인라인 SVG. dataviz 규칙: 얇은 마크(선 2px, 막대 ≤ 24px·끝만 4px 라운드),
 * 눈금선은 연한 실선, 값 라벨은 선택적으로, 텍스트는 잉크 토큰(시리즈 색을 쓰지 않음), 범례는 시리즈 2개 이상일 때 항상,
 * 모든 값은 툴팁과 "표로 보기"로도 읽힌다. 라벨은 신뢰할 수 없는 데이터이므로 전부 textContent 로 넣는다. */
(function (root) {
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, text) => {
    const e = tag.startsWith("svg:") ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const fmtN = (n, d = 0) => (n == null || Number.isNaN(n) ? "–" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: d }));
  const fmtP = (p, d = 1) => (p == null || Number.isNaN(p) ? "–" : (p * 100).toFixed(d) + " %");
  /* viewBox 폭을 컨테이너 폭에 맞춰 글자 크기가 화면 폭과 무관하게 거의 일정하게 보이게 한다 */
  const chartWidth = (container) => Math.round(Math.min(760, Math.max(300, container.clientWidth || 680)));

  /* ---------- 툴팁 ---------- */
  let tip;
  function tooltip() {
    if (!tip) { tip = el("div", { class: "tooltip", hidden: "", role: "status" }); document.body.appendChild(tip); }
    return tip;
  }
  function showTip(x, y, title, rows) {
    const t = tooltip();
    t.replaceChildren();
    if (title) t.appendChild(el("div", { class: "t" }, title));
    for (const r of rows) {
      const row = el("div", { class: "row" });
      const left = el("span");
      if (r.color) { const k = el("span", { class: "k" }); k.style.background = r.color; left.appendChild(k); }
      left.appendChild(document.createTextNode(r.label));
      row.appendChild(left);
      row.appendChild(el("b", {}, r.value));
      t.appendChild(row);
    }
    t.hidden = false;
    const w = t.offsetWidth, h = t.offsetHeight;
    t.style.left = Math.max(8, Math.min(x + 14, window.innerWidth - w - 8)) + "px";
    t.style.top = Math.max(8, y - h - 12) + "px";
  }
  const hideTip = () => { if (tip) tip.hidden = true; };

  function niceTicks(a, b, n) {
    const span = b - a || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((c) => c * mag).find((c) => span / c <= n) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(a / step - 1e-9) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }

  /* ---------- 표로 보기 ---------- */
  function tableView(container, headers, rows, summary = "표로 보기") {
    const d = el("details", { class: "tableview" });
    d.appendChild(el("summary", {}, summary));
    const t = el("table", { class: "data" });
    const tr = el("tr");
    headers.forEach((h, i) => tr.appendChild(el("th", { class: i ? "num" : "" }, h)));
    t.appendChild(el("thead")).appendChild(tr);
    const tb = el("tbody");
    for (const r of rows) {
      const row = el("tr");
      r.forEach((c, i) => row.appendChild(el("td", { class: i ? "num" : "" }, String(c))));
      tb.appendChild(row);
    }
    t.appendChild(tb);
    d.appendChild(t);
    container.appendChild(d);
  }

  /* ---------- 범례 ---------- */
  function legend(items) {
    const lg = el("div", { class: "legend" });
    for (const it of items) {
      const i = el("span");
      const k = el("span", { class: "key" + (it.rect ? " rect" : "") });
      k.style.background = it.color;
      if (it.thin) k.style.height = "1px";
      i.appendChild(k);
      i.appendChild(document.createTextNode(it.label));
      lg.appendChild(i);
    }
    return lg;
  }

  /* ---------- 선 차트 ----------
   * series: [{name, color, points:[{x:number, y:number|null}], markers?, area?, width?, endLabel?}]
   * opts: {height, y0, y1, fmtX, fmtY, xTicks, refY, label, onPick(x), marker:{x}} */
  function lineChart(container, series, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), H = opts.height || 220, m = { l: 48, r: opts.rightPad ?? 16, t: 12, b: 28 };
    const xs = series.flatMap((s) => s.points.map((p) => +p.x));
    const ys = series.flatMap((s) => s.points.map((p) => p.y)).filter((v) => v != null);
    if (!xs.length) { container.appendChild(el("div", { class: "empty" }, "데이터 없음")); return null; }
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = opts.y0 ?? Math.min(0, ...ys), y1 = opts.y1 ?? Math.max(...ys);
    if (y1 === y0) y1 = y0 + 1;
    if (opts.y1 == null) y1 += (y1 - y0) * 0.08;
    const sx = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
    const sy = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    const grid = el("svg:g", { class: "grid" });
    for (const t of niceTicks(y0, y1, 4)) {
      grid.appendChild(el("svg:line", { x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t) }));
      svg.appendChild(el("svg:text", { x: m.l - 6, y: sy(t) + 3, "text-anchor": "end" }, opts.fmtY ? opts.fmtY(t) : fmtN(t, 2)));
    }
    svg.insertBefore(grid, svg.firstChild);
    const base = sy(Math.max(y0, Math.min(0, y1)));
    svg.appendChild(el("svg:g", { class: "axis" })).appendChild(el("svg:line", { x1: m.l, x2: W - m.r, y1: base, y2: base }));
    const xt = opts.xTicks ?? 5;
    for (let i = 0; i <= xt; i++) {
      const v = x0 + ((x1 - x0) * i) / xt;
      svg.appendChild(el("svg:text", { x: sx(v), y: H - 8, "text-anchor": i === 0 ? "start" : i === xt ? "end" : "middle" }, opts.fmtX ? opts.fmtX(v) : fmtN(v)));
    }
    if (opts.refY != null) svg.appendChild(el("svg:line", { x1: m.l, x2: W - m.r, y1: sy(opts.refY), y2: sy(opts.refY), stroke: "var(--axis)", "stroke-width": 1 }));
    for (const s of series) {
      const pts = s.points.filter((p) => p.y != null);
      if (!pts.length) continue;
      const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(+p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join("");
      if (s.area) svg.appendChild(el("svg:path", { class: "area", fill: s.color, d: d + `L${sx(+pts[pts.length - 1].x)},${base}L${sx(+pts[0].x)},${base}Z` }));
      svg.appendChild(el("svg:path", { class: "line", stroke: s.color, "stroke-width": s.width || 2, d }));
      if (s.markers) for (const p of pts) svg.appendChild(el("svg:circle", { class: "marker", cx: sx(+p.x), cy: sy(p.y), r: 4, fill: s.color }));
      if (s.endLabel) {
        const last = pts[pts.length - 1];
        svg.appendChild(el("svg:text", { x: sx(+last.x) + 8, y: sy(last.y) + 4, class: "endlabel" }, s.endLabel(last)));
      }
    }
    let pick = null;
    if (opts.marker != null) {
      const mx = sx(opts.marker);
      svg.appendChild(el("svg:line", { x1: mx, x2: mx, y1: m.t, y2: H - m.b, stroke: "var(--text-primary)", "stroke-width": 1, "stroke-opacity": 0.28 }));
    }
    const cross = el("svg:line", { class: "crosshair", y1: m.t, y2: H - m.b, visibility: "hidden" });
    svg.appendChild(cross);
    const hit = el("svg:rect", { class: "hit", x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, tabindex: "0" });
    const nearest = (clientX) => {
      const r = svg.getBoundingClientRect();
      const xv = x0 + (((clientX - r.left) * W) / r.width - m.l) / (W - m.l - m.r) * (x1 - x0);
      let best = null, bd = Infinity;
      for (const p of series[0].points) { const dd = Math.abs(+p.x - xv); if (dd < bd) { bd = dd; best = p; } }
      return best;
    };
    const rowsAt = (x) => series.map((s) => { const q = s.points.find((p) => +p.x === +x); return { label: s.name, color: s.color, value: q && q.y != null ? (opts.fmtY ? opts.fmtY(q.y) : fmtN(q.y, 2)) : "–" }; });
    hit.addEventListener("pointermove", (ev) => {
      const b = nearest(ev.clientX);
      if (!b) return;
      cross.setAttribute("x1", sx(+b.x)); cross.setAttribute("x2", sx(+b.x)); cross.setAttribute("visibility", "visible");
      showTip(ev.clientX, ev.clientY, opts.fmtX ? opts.fmtX(+b.x) : String(b.x), rowsAt(b.x));
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
    if (opts.onPick) hit.addEventListener("click", (ev) => { const b = nearest(ev.clientX); if (b) opts.onPick(+b.x); });
    svg.appendChild(hit);
    if (series.length > 1) container.appendChild(legend(series.map((s) => ({ label: s.name, color: s.color, thin: s.width === 1 }))));
    container.appendChild(svg);
    if (opts.table) tableView(container, opts.table.headers, opts.table.rows);
    return pick;
  }

  /* ---------- 가로 막대 ----------
   * rows: [{label, value, color?, sub?, lo?, hi?, note?}] — 음수 허용(발산), lo/hi 가 있으면 신뢰구간 수염 */
  function hbars(container, rows, opts = {}) {
    container.replaceChildren();
    if (!rows.length) { container.appendChild(el("div", { class: "empty" }, "데이터 없음")); return; }
    const W = chartWidth(container), bh = opts.barHeight || 18, gap = opts.gap || 10, labelW = Math.min(opts.labelW || 150, Math.round(W * 0.46)), valueW = opts.valueW || 74, H = rows.length * (bh + gap) + 6;
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    const vals = rows.flatMap((r) => [r.value, r.hi ?? r.value]);
    const neg = Math.min(0, ...rows.map((r) => r.value)), pos = Math.max(opts.max ?? 0, ...vals);
    const x0 = labelW, x1 = W - valueW, sx = (v) => x0 + ((v - neg) / (pos - neg || 1)) * (x1 - x0), zero = sx(0);
    svg.appendChild(el("svg:line", { x1: zero, x2: zero, y1: 0, y2: H, stroke: "var(--axis)" }));
    rows.forEach((r, i) => {
      const y = 3 + i * (bh + gap), w = Math.max(1, Math.abs(sx(r.value) - zero)), rx = 4;
      const color = r.color || (r.value < 0 ? "var(--div-neg)" : opts.diverging ? "var(--div-pos)" : "var(--series-1)");
      const d = r.value >= 0
        ? `M${zero},${y}h${Math.max(0, w - rx)}a${rx},${rx} 0 0 1 ${rx},${rx}v${bh - 2 * rx}a${rx},${rx} 0 0 1 -${rx},${rx}h-${Math.max(0, w - rx)}z`
        : `M${zero},${y}h-${Math.max(0, w - rx)}a${rx},${rx} 0 0 0 -${rx},${rx}v${bh - 2 * rx}a${rx},${rx} 0 0 0 ${rx},${rx}h${Math.max(0, w - rx)}z`;
      const p = el("svg:path", { d, fill: color, class: "bar-mark", tabindex: "0" });
      const tipRows = [{ label: opts.valueName || "값", value: opts.fmt ? opts.fmt(r.value) : fmtN(r.value, 3) }];
      if (r.lo != null) tipRows.push({ label: "95% 신뢰구간", value: `${opts.fmt ? opts.fmt(r.lo) : r.lo} ~ ${opts.fmt ? opts.fmt(r.hi) : r.hi}` });
      if (r.sub) tipRows.push({ label: "", value: r.sub });
      const show = (ev) => { const b = (ev.currentTarget || p).getBoundingClientRect(); showTip(ev.clientX || b.left + b.width / 2, ev.clientY || b.top, r.label, tipRows); };
      p.addEventListener("pointermove", show); p.addEventListener("focus", show);
      p.addEventListener("pointerleave", hideTip); p.addEventListener("blur", hideTip);
      svg.appendChild(p);
      if (r.lo != null && r.hi != null) {
        const cy = y + bh / 2;
        const g = el("svg:g", { stroke: "var(--text-secondary)", "stroke-width": 1.5 });
        g.appendChild(el("svg:line", { x1: sx(r.lo), x2: sx(r.hi), y1: cy, y2: cy }));
        g.appendChild(el("svg:line", { x1: sx(r.lo), x2: sx(r.lo), y1: cy - 4, y2: cy + 4 }));
        g.appendChild(el("svg:line", { x1: sx(r.hi), x2: sx(r.hi), y1: cy - 4, y2: cy + 4 }));
        svg.appendChild(g);
      }
      const maxChars = Math.max(8, Math.floor((labelW - 10) / 7.2)), lab = r.label.length > maxChars ? r.label.slice(0, maxChars - 1) + "…" : r.label;
      svg.appendChild(el("svg:text", { x: labelW - 8, y: y + bh / 2 + 4, "text-anchor": "end", class: "rowlabel" }, lab));
      const tx = (r.hi != null ? sx(r.hi) : r.value >= 0 ? sx(r.value) : sx(r.value)) + (r.value >= 0 ? 8 : -8);
      svg.appendChild(el("svg:text", { x: tx, y: y + bh / 2 + 4, "text-anchor": r.value >= 0 ? "start" : "end", class: "valuelabel" }, opts.fmt ? opts.fmt(r.value) : fmtN(r.value, 3)));
    });
    container.appendChild(svg);
    if (opts.table !== false) tableView(container, ["항목", opts.valueName || "값", ...(rows.some((r) => r.lo != null) ? ["95% 신뢰구간", "n"] : [])],
      rows.map((r) => [r.label, opts.fmt ? opts.fmt(r.value) : fmtN(r.value, 3), ...(r.lo != null ? [`${opts.fmt ? opts.fmt(r.lo) : r.lo} ~ ${opts.fmt ? opts.fmt(r.hi) : r.hi}`, r.note ?? ""] : [])]));
  }

  /* ---------- 표 ---------- */
  function table(container, cols, rows, onRow) {
    container.replaceChildren();
    if (!rows.length) { container.appendChild(el("div", { class: "empty" }, "데이터 없음")); return; }
    const t = el("table", { class: "data" });
    const tr = el("tr");
    for (const c of cols) tr.appendChild(el("th", { class: (c.num ? "num " : "") + (c.nowrap ? "nowrap" : "") }, c.h));
    t.appendChild(el("thead")).appendChild(tr);
    const tb = el("tbody");
    for (const r of rows) {
      const row = el("tr", { class: onRow ? "clickable" : "", tabindex: onRow ? "0" : null });
      for (const c of cols) {
        const td = el("td", { class: (c.num ? "num " : "") + (c.nowrap ? "nowrap" : "") });
        const v = c.render ? c.render(r) : r[c.k];
        if (v instanceof Node) td.appendChild(v); else td.textContent = v == null ? "–" : String(v);
        row.appendChild(td);
      }
      if (onRow) {
        row.addEventListener("click", () => onRow(r));
        row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(r); } });
      }
      tb.appendChild(row);
    }
    t.appendChild(tb);
    container.appendChild(t);
  }

  /* ---------- 작은 부품 ---------- */
  function pbar(p, max = 0.5, width = 110) {
    const wrap = el("span", { class: "pbar" });
    const tr = el("span", { class: "bar-track" });
    tr.style.width = width + "px";
    const b = el("span", { class: "bar" });
    b.style.width = Math.max(2, Math.min(1, p / max) * width) + "px";
    tr.appendChild(b);
    wrap.appendChild(tr);
    wrap.appendChild(document.createTextNode(fmtP(p)));
    return wrap;
  }
  function badge(kind, text) {
    const b = el("span", { class: `badge ${kind}` });
    b.appendChild(el("span", { class: "dot", "aria-hidden": "true" }));
    b.appendChild(document.createTextNode(text));
    return b;
  }
  function tile(label, value, sub, subCls) {
    const t = el("div", { class: "tile" });
    t.appendChild(el("div", { class: "label" }, label));
    t.appendChild(el("div", { class: "value" }, value));
    if (sub) t.appendChild(el("div", { class: `delta ${subCls || ""}` }, sub));
    return t;
  }

  /* ---------- 사건 타임라인 ----------
   * rows: [{label, ticks:[{x, hit?, tip?}], color?}]  — hit === false 는 속이 빈 점(정답과 안 맞는 사건)
   * opts: {x0, x1, fmtX, rowH, labelW, label} */
  function timeline(container, rows, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), rowH = opts.rowH || 26, labelW = Math.min(opts.labelW || 130, Math.round(W * 0.3)), H = rows.length * rowH + 28;
    const x0 = opts.x0 ?? 0, x1 = opts.x1 ?? 1, sx = (v) => labelW + ((v - x0) / (x1 - x0 || 1)) * (W - labelW - 10);
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    const grid = el("svg:g", { class: "grid" });
    for (const t of niceTicks(x0, x1, 6)) {
      grid.appendChild(el("svg:line", { x1: sx(t), x2: sx(t), y1: 0, y2: rows.length * rowH }));
      svg.appendChild(el("svg:text", { x: sx(t), y: rows.length * rowH + 16, "text-anchor": "middle" }, opts.fmtX ? opts.fmtX(t) : fmtN(t)));
    }
    svg.appendChild(grid);
    rows.forEach((r, i) => {
      const cy = i * rowH + rowH / 2;
      svg.appendChild(el("svg:text", { x: labelW - 8, y: cy + 4, "text-anchor": "end", class: "rowlabel" }, r.label));
      svg.appendChild(el("svg:line", { x1: labelW, x2: W - 10, y1: cy, y2: cy, stroke: "var(--grid)", "stroke-width": 1 }));
      const color = r.color || "var(--series-1)";
      for (const t of r.ticks) {
        const hollow = t.hit === false;
        const c = el("svg:circle", { cx: sx(t.x), cy, r: 3, fill: hollow ? "var(--surface-1)" : color, stroke: color, "stroke-width": 1.4, class: "bar-mark" });
        if (t.tip) {
          c.addEventListener("pointermove", (ev) => showTip(ev.clientX, ev.clientY, r.label, t.tip));
          c.addEventListener("pointerleave", hideTip);
        }
        svg.appendChild(c);
      }
    });
    container.appendChild(svg);
  }

  /* ---------- 히트맵 ----------
   * values[r][c] 는 0~1 (null 이면 빈 칸). 색 진하기 = 값. 칸 안에 값을 적고 툴팁에도 낸다. */
  function heatmap(container, rowLabels, colLabels, values, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), labelW = Math.min(opts.labelW || 92, Math.round(W * 0.24)), headH = opts.headH || 34, cellH = opts.cellH || 30;
    const cw = (W - labelW) / colLabels.length, H = headH + rowLabels.length * cellH + 4;
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    colLabels.forEach((c, j) => {
      const t = el("svg:text", { x: labelW + j * cw + cw / 2, y: headH - 10, "text-anchor": "middle", class: "rowlabel" });
      const parts = String(c).split("\n");
      parts.forEach((p, k) => t.appendChild(el("svg:tspan", { x: labelW + j * cw + cw / 2, dy: k ? 13 : -(parts.length - 1) * 6.5 }, p)));
      svg.appendChild(t);
    });
    const fmt = opts.fmt || ((v) => v.toFixed(2));
    rowLabels.forEach((rl, i) => {
      svg.appendChild(el("svg:text", { x: labelW - 8, y: headH + i * cellH + cellH / 2 + 4, "text-anchor": "end", class: "rowlabel" }, rl));
      colLabels.forEach((cl, j) => {
        const v = values[i][j];
        const g = el("svg:g");
        const pct = v == null ? 0 : Math.round(8 + 52 * Math.max(0, Math.min(1, (v - (opts.lo ?? 0)) / ((opts.hi ?? 1) - (opts.lo ?? 0) || 1))));
        const rect = el("svg:rect", { x: labelW + j * cw + 1, y: headH + i * cellH + 1, width: cw - 2, height: cellH - 2, rx: 4, class: "bar-mark", tabindex: v == null ? null : "0" });
        rect.style.fill = v == null ? "transparent" : `color-mix(in srgb, var(--series-1) ${pct}%, var(--surface-1))`;
        rect.style.stroke = "var(--grid)";
        g.appendChild(rect);
        if (v != null) {
          g.appendChild(el("svg:text", { x: labelW + j * cw + cw / 2, y: headH + i * cellH + cellH / 2 + 4, "text-anchor": "middle", class: "valuelabel" }, fmt(v)));
          const show = (ev) => { const b = rect.getBoundingClientRect(); showTip(ev.clientX || b.left + b.width / 2, ev.clientY || b.top, `${rl} · ${String(cl).replace("\n", " ")}`, [{ label: opts.valueName || "값", value: fmt(v) }, ...((opts.extra && opts.extra(i, j)) || [])]); };
          rect.addEventListener("pointermove", show); rect.addEventListener("focus", show);
          rect.addEventListener("pointerleave", hideTip); rect.addEventListener("blur", hideTip);
        }
        svg.appendChild(g);
      });
    });
    container.appendChild(svg);
    if (opts.table !== false) tableView(container, ["", ...colLabels.map((c) => String(c).replace("\n", " "))], rowLabels.map((rl, i) => [rl, ...values[i].map((v) => (v == null ? "–" : fmt(v)))]));
  }

  /* ---------- 두 값 비교 (덤벨) ----------
   * rows: [{label, a, b, sub?}] — a 는 속이 빈 고리, b 는 채운 점. 둘 사이를 선으로 잇는다. */
  function dumbbell(container, rows, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), gap = 30, labelW = Math.min(opts.labelW || 160, Math.round(W * 0.38)), H = rows.length * gap + 30;
    const vals = rows.flatMap((r) => [r.a, r.b]);
    const lo = opts.min ?? Math.floor((Math.min(...vals) - 0.02) * 20) / 20, hi = opts.max ?? Math.ceil((Math.max(...vals) + 0.02) * 20) / 20;
    const sx = (v) => labelW + ((v - lo) / (hi - lo || 1)) * (W - labelW - 56);
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    const grid = el("svg:g", { class: "grid" });
    for (const t of niceTicks(lo, hi, 5)) {
      grid.appendChild(el("svg:line", { x1: sx(t), x2: sx(t), y1: 0, y2: rows.length * gap }));
      svg.appendChild(el("svg:text", { x: sx(t), y: rows.length * gap + 16, "text-anchor": "middle" }, (opts.fmt || ((v) => v.toFixed(2)))(t)));
    }
    svg.appendChild(grid);
    const fmt = opts.fmt || ((v) => v.toFixed(3));
    rows.forEach((r, i) => {
      const cy = i * gap + gap / 2;
      svg.appendChild(el("svg:text", { x: labelW - 8, y: cy + 4, "text-anchor": "end", class: "rowlabel" }, r.label));
      svg.appendChild(el("svg:line", { x1: sx(r.a), x2: sx(r.b), y1: cy, y2: cy, stroke: "var(--axis)", "stroke-width": 2 }));
      const ring = el("svg:circle", { cx: sx(r.a), cy, r: 5.5, fill: "var(--surface-1)", stroke: opts.colorA || "var(--series-2)", "stroke-width": 2, tabindex: "0", class: "bar-mark" });
      const dot = el("svg:circle", { cx: sx(r.b), cy, r: 5, fill: opts.colorB || "var(--series-1)", class: "marker", tabindex: "0" });
      for (const [node, name] of [[ring, opts.nameA || "A"], [dot, opts.nameB || "B"]]) {
        const show = (ev) => { const b = node.getBoundingClientRect(); showTip(ev.clientX || b.left, ev.clientY || b.top, r.label, [{ label: opts.nameA || "A", value: fmt(r.a) }, { label: opts.nameB || "B", value: fmt(r.b) }, ...(r.sub ? [{ label: "", value: r.sub }] : [])]); };
        node.addEventListener("pointermove", show); node.addEventListener("focus", show); node.addEventListener("pointerleave", hideTip); node.addEventListener("blur", hideTip);
      }
      svg.appendChild(ring); svg.appendChild(dot);
      svg.appendChild(el("svg:text", { x: Math.max(sx(r.a), sx(r.b)) + 12, y: cy + 4, class: "endlabel" }, `${fmt(r.a)} → ${fmt(r.b)}`));
    });
    container.appendChild(svg);
    if (opts.table !== false) tableView(container, ["항목", opts.nameA || "A", opts.nameB || "B"], rows.map((r) => [r.label, fmt(r.a), fmt(r.b)]));
  }

  /* ---------- 추정과 구간, 정답 ----------
   * rows: [{label, est, lo, hi, truth, picked?}] — 점 = 추정, 선 = 구간, 마름모 = 정답 */
  function intervals(container, rows, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), gap = 28, labelW = Math.min(opts.labelW || 150, Math.round(W * 0.36)), H = rows.length * gap + 30;
    const lo = opts.min ?? 0, hi = opts.max ?? 1, sx = (v) => labelW + ((v - lo) / (hi - lo || 1)) * (W - labelW - 20);
    const fmt = opts.fmt || ((v) => v.toFixed(2));
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    const grid = el("svg:g", { class: "grid" });
    for (const t of niceTicks(lo, hi, 5)) {
      grid.appendChild(el("svg:line", { x1: sx(t), x2: sx(t), y1: 0, y2: rows.length * gap }));
      svg.appendChild(el("svg:text", { x: sx(t), y: rows.length * gap + 16, "text-anchor": "middle" }, fmt(t)));
    }
    svg.appendChild(grid);
    rows.forEach((r, i) => {
      const cy = i * gap + gap / 2;
      svg.appendChild(el("svg:text", { x: labelW - 8, y: cy + 4, "text-anchor": "end", class: r.picked ? "valuelabel" : "rowlabel" }, (r.picked ? "▶ " : "") + r.label));
      const g = el("svg:g", { stroke: "var(--text-secondary)", "stroke-width": 1.5 });
      g.appendChild(el("svg:line", { x1: sx(r.lo), x2: sx(r.hi), y1: cy, y2: cy }));
      g.appendChild(el("svg:line", { x1: sx(r.lo), x2: sx(r.lo), y1: cy - 4, y2: cy + 4 }));
      g.appendChild(el("svg:line", { x1: sx(r.hi), x2: sx(r.hi), y1: cy - 4, y2: cy + 4 }));
      svg.appendChild(g);
      const dot = el("svg:circle", { cx: sx(r.est), cy, r: 5, fill: "var(--series-1)", class: "marker", tabindex: "0" });
      const dia = el("svg:path", { d: `M${sx(r.truth)},${cy - 6}L${sx(r.truth) + 6},${cy}L${sx(r.truth)},${cy + 6}L${sx(r.truth) - 6},${cy}Z`, fill: "var(--surface-1)", stroke: "var(--series-2)", "stroke-width": 1.8, tabindex: "0" });
      for (const node of [dot, dia]) {
        const show = (ev) => { const b = node.getBoundingClientRect(); showTip(ev.clientX || b.left, ev.clientY || b.top, r.label, [{ label: "추정", value: fmt(r.est) }, { label: "90% 구간", value: `${fmt(r.lo)} ~ ${fmt(r.hi)}` }, { label: "정답", value: fmt(r.truth) }]); };
        node.addEventListener("pointermove", show); node.addEventListener("focus", show); node.addEventListener("pointerleave", hideTip); node.addEventListener("blur", hideTip);
      }
      svg.appendChild(dia); svg.appendChild(dot);
    });
    container.appendChild(svg);
    if (opts.table !== false) tableView(container, ["정의", "추정", "90% 구간", "정답"], rows.map((r) => [r.label, fmt(r.est), `${fmt(r.lo)} ~ ${fmt(r.hi)}`, fmt(r.truth)]));
  }

  /* ---------- 묶음 막대 ----------
   * groups: 문자열 배열, series: [{name, color}], values[g][s]. 막대 끝에 값을 적는다. */
  function groupedBars(container, groups, series, values, opts = {}) {
    container.replaceChildren();
    const W = chartWidth(container), bh = 11, sgap = 3, ggap = 14, labelW = Math.min(opts.labelW || 92, Math.round(W * 0.24)), valueW = 40;
    const gh = series.length * (bh + sgap) - sgap, H = groups.length * (gh + ggap) + 4;
    const max = opts.max ?? Math.max(...values.flat().filter((v) => v != null));
    const sx = (v) => labelW + (v / (max || 1)) * (W - labelW - valueW);
    const fmt = opts.fmt || ((v) => v.toFixed(1));
    const svg = el("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label || "" });
    svg.appendChild(el("svg:line", { x1: labelW, x2: labelW, y1: 0, y2: H, stroke: "var(--axis)" }));
    groups.forEach((g, gi) => {
      const y0 = gi * (gh + ggap) + 2;
      svg.appendChild(el("svg:text", { x: labelW - 8, y: y0 + gh / 2 + 4, "text-anchor": "end", class: "rowlabel" }, g));
      series.forEach((s, si) => {
        const v = values[gi][si];
        if (v == null) return;
        const y = y0 + si * (bh + sgap), w = Math.max(1, sx(v) - labelW);
        const bar = el("svg:path", { d: `M${labelW},${y}h${Math.max(0, w - 3)}a3,3 0 0 1 3,3v${bh - 6}a3,3 0 0 1 -3,3h-${Math.max(0, w - 3)}z`, fill: s.color, class: "bar-mark", tabindex: "0" });
        const show = (ev) => { const b = bar.getBoundingClientRect(); showTip(ev.clientX || b.left, ev.clientY || b.top, g, [{ label: s.name, value: fmt(v), color: s.color }]); };
        bar.addEventListener("pointermove", show); bar.addEventListener("focus", show); bar.addEventListener("pointerleave", hideTip); bar.addEventListener("blur", hideTip);
        svg.appendChild(bar);
        svg.appendChild(el("svg:text", { x: sx(v) + 6, y: y + bh - 2, class: "endlabel" }, fmt(v)));
      });
    });
    container.appendChild(legend(series.map((s) => ({ label: s.name, color: s.color, rect: true }))));
    container.appendChild(svg);
    if (opts.table !== false) tableView(container, ["", ...series.map((s) => s.name)], groups.map((g, gi) => [g, ...values[gi].map((v) => (v == null ? "–" : fmt(v)))]));
  }

  root.FaultlineCharts = { el, fmtN, fmtP, showTip, hideTip, lineChart, hbars, table, tableView, legend, pbar, badge, tile, niceTicks, timeline, heatmap, dumbbell, intervals, groupedBars };
})(typeof self !== "undefined" ? self : this);
