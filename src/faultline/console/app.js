/* faultline 콘솔 — 정적 데모(window.FAULTLINE_STATIC)와 라이브 API 가 같은 코드로 돈다. 서버가 준 문자열은 전부 textContent 로 넣는다. */
(function () {
  const C = window.FaultlineCharts, el = C.el;
  const STATIC = !!window.FAULTLINE_STATIC;
  const $ = (id) => document.getElementById(id);
  const slug = (p) => p.replace(/^\/+/, "").replace(/\//g, "_");
  async function api(path, opts) {
    const r = await fetch(STATIC ? `api/${slug(path)}.json` : path, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} ${m}`); }
    return r.json();
  }
  const f3 = (v) => (v == null ? "–" : Number(v).toFixed(3));
  const f2 = (v) => (v == null ? "–" : Number(v).toFixed(2));
  const pc = (v, d = 0) => (v == null ? "–" : (v * 100).toFixed(d) + "%");
  const sg = (v) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);
  const ARCH = ["표준", "긴급 안 씀", "긴급 남용", "입력 누락", "늦게 입력", "코드 다름"];
  const DEF = {
    d1_emergency: "d1 긴급만", d2_corrective: "d2 시정 포함", d3_corroborated: "d3 민원이 받쳐 주는 것",
    d4_complaint_confirmed: "d4 민원이 확인한 것", d5_emergency_loose: "d5 긴급, 병합 넓게", d6_corroborated_first_record: "d6 d3, 입력 시각 기준",
  };
  const DEFS = Object.keys(DEF);
  const dshort = (n) => (n === "truth" ? "진짜" : n.split("_")[0]);
  const CAT = { ahu: "공조기", chiller: "냉동기", boiler: "보일러", pump: "펌프", fire_pump: "소방펌프", elevator: "승강기", generator: "발전기", switchgear: "수배전반" };
  const SIG = { np_rate: "비예방 작업지시 건수", em_share: "긴급 비중", unknown_share: "분류 불가 비중", missing_share: "설비 번호 누락 비중", link_share: "작업지시와 이어지는 민원 비중" };
  const COL = { d1_emergency: "var(--series-2)", d2_corrective: "var(--series-1)", d3_corroborated: "var(--series-3)" };
  const S = { sum: null, same: null, rank: null, audit: null, mon: null, defs: null, schema: null, qraw: null, qbook: null, hm: "recall", qmode: "raw" };

  function text(tag, cls, t) { const e = el(tag, cls ? { class: cls } : {}); e.textContent = t; return e; }
  function put(id, ...nodes) { const n = $(id); n.replaceChildren(...nodes); return n; }
  const kv = (rows) => rows.map(([k, v]) => ({ label: k, value: v }));

  /* ------------------------------------------------------------------ 초기화 */
  async function init() {
    const saved = (() => { try { return localStorage.getItem("faultline-theme"); } catch (_) { return null; } })();
    if (saved) document.documentElement.dataset.theme = saved;
    $("theme").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("faultline-theme", next); } catch (_) {}
      renderAll();
    });
    document.querySelectorAll("nav.tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
    document.querySelectorAll("details.more").forEach((d) => d.addEventListener("toggle", () => { if (d.open && S.same) renderAll(); }));
    const hash = location.hash.replace("#", "");
    if (hash) showTab(hash, false);
    try {
      const [v, same, rank, audit, mon] = await Promise.all([api("/version"), api("/v1/screens/same-log"), api("/v1/screens/ranking"), api("/v1/screens/audit"), api("/v1/screens/monitor")]);
      S.ver = v; S.sum = v.summary; S.same = same; S.rank = rank; S.audit = audit; S.mon = mon;
    } catch (e) { put("hero", text("div", "err", "산출물을 불러오지 못했다: " + e.message)); return; }
    api("/v1/definitions").then((d) => { S.defs = d; renderDefine(); renderBring(); }).catch(() => {});
    api("/v1/schema").then((d) => { S.schema = d; renderBring(); }).catch(() => {});
    S.qraw = S.same.quality.report_without_code_book;
    S.qbook = S.same.quality.report_with_code_book;
    const m = S.ver.manifest;
    if (m) $("foot-meta").textContent = `v${S.ver.version} · 시드 ${m.base_seeds.join(", ")}`;
    setupControls();
    renderAll();
  }

  function showTab(name, push = true) {
    document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll("section.tab").forEach((s) => (s.hidden = s.id !== "tab-" + name));
    if (push) { try { history.replaceState(null, "", "#" + name); } catch (_) {} }
    if (S.same) renderAll();
  }
  const activeTab = () => (document.querySelector("nav.tabs button[aria-selected=true]") || {}).dataset.tab;

  function setupControls() {
    $("def-arch").replaceChildren(...ARCH.map((a) => { const o = el("option", { value: a }); o.textContent = a; return o; }));
    $("def-arch").value = "긴급 안 씀";
    $("def-arch").addEventListener("change", renderDefine);
    $("def-range").addEventListener("change", renderDefine);
    for (const [id, key] of [["hm-recall", "recall"], ["hm-prec", "precision"]]) {
      $(id).addEventListener("click", () => { S.hm = key; $("hm-recall").setAttribute("aria-pressed", String(key === "recall")); $("hm-prec").setAttribute("aria-pressed", String(key === "precision")); renderHeat(); });
    }
    $("def-pick").replaceChildren(...DEFS.map((n) => { const o = el("option", { value: n }); o.textContent = DEF[n]; return o; }));
    $("def-pick").value = "d3_corroborated";
    $("def-pick").addEventListener("change", renderDefFile);
    const ex = S.rank.base.topk.examples;
    $("rk-ex").replaceChildren(...ex.map((e, i) => { const o = el("option", { value: String(i) }); o.textContent = `${e.archetype} 사이트 ${e.site}, ${e.week}주`; return o; }));
    $("rk-ex").addEventListener("change", renderExample);
    const sites = Object.entries(S.audit.demo.sites);
    $("au-site").replaceChildren(...sites.map(([s, v]) => { const o = el("option", { value: s }); o.textContent = `사이트 ${s} · ${v.archetype}`; return o; }));
    $("au-site").value = "1";
    $("au-site").addEventListener("change", renderAuditSim);
    $("au-n").addEventListener("input", renderAuditSim);
    const shifted = new Map(S.mon.series.shifts.map(([s, , to]) => [String(s), to]));
    $("mo-site").replaceChildren(...Object.keys(S.mon.series.sites).map((s) => { const o = el("option", { value: s }); o.textContent = `사이트 ${s}` + (shifted.has(s) ? ` (100주에 '${shifted.get(s)}'로 변경)` : ""); return o; }));
    $("mo-site").value = "12";
    const sigs = Object.keys(S.mon.series.sites["0"].signals);
    $("mo-sig").replaceChildren(...sigs.map((n) => { const o = el("option", { value: n }); o.textContent = SIG[n] || n; return o; }));
    $("mo-sig").value = "em_share";
    $("mo-site").addEventListener("change", renderMonitor);
    $("mo-sig").addEventListener("change", renderMonitor);
    $("q-raw").addEventListener("click", () => { S.qmode = "raw"; $("q-raw").setAttribute("aria-pressed", "true"); $("q-book").setAttribute("aria-pressed", "false"); renderQuality(); });
    $("q-book").addEventListener("click", () => { S.qmode = "book"; $("q-raw").setAttribute("aria-pressed", "false"); $("q-book").setAttribute("aria-pressed", "true"); renderQuality(); });
  }

  function renderAll() {
    if (!S.same) return;
    renderHero();
    const t = activeTab();
    ({ define: renderDefine, rank: renderRank, audit: renderAudit, quality: renderQuality, monitor: renderMonitor, bring: renderBring }[t] || (() => {}))();
  }

  /* ------------------------------------------------------------------ 상단 */
  function renderHero() {
    const s = S.sum;
    put("world-note", document.createTextNode(`합성 세계 ${S.same.world.sites}개 사이트, 설비 ${C.fmtN(S.same.world.assets)}개, 3년. 작업지시 ${C.fmtN(S.same.world.work_orders)}건, 민원 ${C.fmtN(S.same.world.complaints)}건, 진짜 고장 ${C.fmtN(S.same.world.failures)}건(시뮬레이터가 안다).`));
    put("hero",
      C.tile("같은 로그, 정의만 바꾼 두 모형", `${f3(s.auc.d1)} → ${f3(s.auc.d2)}`, `진짜 고장 맞히기(AUC). 시드 ${s.worlds.base_seeds}개 중 ${s.auc.d2_beats_d1_seeds}개에서 d2가 높다`),
      C.tile("d1을 자기 라벨로 채점하면", f3(s.apparent.d1_own_auc), `진짜 고장으로는 ${f3(s.apparent.d1_truth_auc)}. 겉보기 1위가 진짜로는 하위다`, "bad"),
      C.tile("긴급 코드를 안 쓰는 사이트에서 d1이 잡은 고장", pc(s.labels.d1_recall_no_emergency_sites), `표준 사이트에서는 ${pc(s.labels.d1_recall_standard_sites)}`, "bad"));
  }

  /* ------------------------------------------------------------------ 1. 고장 정의 */
  function renderDefine() {
    if (!S.same) return;
    const a = $("def-arch").value, rng = +$("def-range").value;
    const tl = S.same.timeline, site = tl.sites[a], W = tl.weeks, x0 = W - rng;
    const byAsset = {};
    for (const f of site.failures) (byAsset[f.asset] = byAsset[f.asset] || []).push(f.day);
    const near = (asset, day) => (byAsset[asset] || []).some((d) => Math.abs(d - day) <= 14);
    const inRange = (day) => day / 7 >= x0;
    const names = ["d1_emergency", "d2_corrective", "d3_corroborated"];
    const rows = [{ label: "진짜 고장", color: "var(--text-primary)", ticks: site.failures.filter((f) => inRange(f.day)).map((f) => ({ x: f.day / 7, tip: kv([["설비", "#" + f.asset], ["주", String(Math.floor(f.day / 7))]]) })) }];
    const summary = [];
    for (const n of names) {
      const inc = site.definitions[n].filter((i) => inRange(i.day));
      const ticks = inc.map((i) => ({ x: i.day / 7, hit: near(i.asset, i.day), tip: kv([["설비", "#" + i.asset], ["주", String(Math.floor(i.day / 7))], ["증거", i.evidence], ["진짜 고장과", near(i.asset, i.day) ? "맞음" : "안 맞음"]]) }));
      rows.push({ label: DEF[n].split(" ")[0] + " " + DEF[n].split(" ")[1], color: COL[n], ticks });
      const missed = site.failures.filter((f) => inRange(f.day) && !site.definitions[n].some((i) => i.asset === f.asset && Math.abs(i.day - f.day) <= 14)).length;
      summary.push({ name: DEF[n], n: ticks.length, hit: ticks.filter((t) => t.hit).length, missed });
    }
    const nTruth = rows[0].ticks.length;
    $("def-sub").textContent = `${a} 사이트(사이트 ${site.site}, 설비 ${site.n_assets}개). 이 기간 진짜 고장 ${nTruth}건. 속이 빈 점은 진짜 고장과 맞지 않는 사건이다.`;
    const chart = el("div"), tab = el("div");
    put("def-timeline", chart, tab);
    C.timeline(chart, rows, { x0, x1: W, fmtX: (v) => Math.round(v) + "주", label: "정의별 사건 타임라인" });
    tab.appendChild(text("div", "sub", "d1 긴급 유형 작업지시만 · d2 긴급과 시정 작업지시 모두 · d3 긴급이거나 같은 증상의 민원이 받쳐 주는 작업지시(민원 군집 포함)"));
    C.table(tab, [
      { h: "정의", k: "name" },
      { h: "사건", k: "n", num: true },
      { h: "맞음", render: (r) => `${r.hit} (${pc(r.n ? r.hit / r.n : 0)})`, num: true },
      { h: "놓친 고장", render: (r) => `${r.missed} / ${nTruth}`, num: true },
    ], summary);
    renderHeat();
    renderDefFile();
    const defs = S.same.labels.definitions;
    C.table($("def-table"), [
      { h: "정의", render: (r) => DEF[r.n] },
      { h: "사건", render: (r) => C.fmtN(r.o.incidents), num: true },
      { h: "정밀도", render: (r) => pc(r.o.precision), num: true },
      { h: "재현율", render: (r) => pc(r.o.recall), num: true },
      { h: "F1", render: (r) => f2(r.o.f1), num: true },
      { h: "시각 오차 중앙값(일)", render: (r) => r.o.timing_median, num: true },
    ], DEFS.map((n) => ({ n, o: defs[n].overall })));
  }

  function renderHeat() {
    const defs = S.same.labels.definitions, key = S.hm;
    const vals = ARCH.map((a) => DEFS.map((n) => defs[n].by_archetype[a][key]));
    const box = $("def-heat");
    const chart = el("div");
    box.replaceChildren(chart, text("div", "sub", DEFS.map((n) => DEF[n]).join(" · ")));
    C.heatmap(chart, ARCH, DEFS.map(dshort), vals, { fmt: (v) => pc(v), valueName: key === "recall" ? "재현율" : "정밀도", label: "습관별 라벨 품질" });
  }

  function renderDefFile() {
    if (!S.defs) { put("def-yaml", document.createTextNode("")); return; }
    const n = $("def-pick").value, d = S.defs.definitions.find((x) => x.name === n);
    if (!d) return;
    $("def-desc").textContent = d.description;
    $("def-yaml").textContent = d.yaml;
  }

  /* ------------------------------------------------------------------ 2. 점검 순서 */
  function renderRank() {
    const R = S.rank, m = R.multi.base, s = S.sum;
    const box = $("rk-dumbbell");
    const chart = el("div");
    box.replaceChildren(C.legend([{ label: "자기 라벨로 채점", color: "var(--series-2)" }, { label: "진짜 고장으로 채점", color: "var(--series-1)" }]), chart);
    C.dumbbell(chart, DEFS.map((n) => ({ label: DEF[n], a: m.models[n].own_auc.mean, b: m.models[n].truth_auc.mean, sub: `진짜 AUC 범위 ${f3(m.models[n].truth_auc.min)} ~ ${f3(m.models[n].truth_auc.max)}` })), { nameA: "자기 라벨", nameB: "진짜 고장", labelW: 170, min: 0.5, max: 0.8, fmt: (v) => v.toFixed(3), label: "자기 라벨과 진짜 고장으로 채점" });
    $("rk-sub").textContent = `시드 ${m.seeds.length}개 평균. 평가 구간 주 104~151. 자기 라벨로 고른 1위가 진짜 1위와 같았던 시드는 ${s.apparent.best_by_own_is_best_by_truth}개다.`;
    const o = R.base.overlap;
    const idx = o.names.map((n) => dshort(n));
    C.heatmap($("rk-overlap"), idx, idx, o.matrix, { fmt: (v) => v.toFixed(2), lo: 0, hi: 0.6, valueName: "겹침", label: "상위 5곳 겹침", labelW: 56, cellH: 28 });
    const per = R.base.topk.per100_by_archetype;
    const ser = [
      { name: "d1", color: COL.d1_emergency }, { name: "d2", color: COL.d2_corrective }, { name: "d3", color: COL.d3_corroborated },
      { name: "진짜 라벨로 학습", color: "var(--text-secondary)" }, { name: "무작위", color: "var(--deemph)" },
    ];
    C.groupedBars($("rk-arch"), ARCH, ser, ARCH.map((a) => [per[a].d1_emergency, per[a].d2_corrective, per[a].d3_corroborated, per[a].truth, per[a].random]), { fmt: (v) => v.toFixed(1), label: "습관별 점검 적중" });
    const no = per["긴급 안 씀"], st = per["표준"];
    put("rk-note", ...[
      ["b", `d1은 표준 습관 사이트에서 가장 잘 맞는다(${st.d1_emergency.toFixed(1)}, d3 ${st.d3_corroborated.toFixed(1)}).`],
      ["span", ` 긴급 코드를 안 쓰는 사이트에서는 ${no.d1_emergency.toFixed(1)}로 무작위(${no.random.toFixed(1)})에 가깝고, d3는 ${no.d3_corroborated.toFixed(1)}다. 정의 하나가 모든 사이트에서 최선이지는 않다.`],
    ].map(([t, x]) => text(t, "", x)));
    renderExample();
    const u = R.multi.uniform, b = R.multi.base;
    C.table($("rk-uniform"), [
      { h: "정의", render: (r) => (r.spread ? "정의 사이의 차이(최대−최소)" : DEF[r.n]) },
      { h: "습관이 다른 세계", render: (r) => f3(r.spread ? b.auc_spread.mean : b.models[r.n].truth_auc.mean), num: true },
      { h: "습관이 같은 세계", render: (r) => f3(r.spread ? u.auc_spread.mean : u.models[r.n].truth_auc.mean), num: true },
    ], [...DEFS.map((n) => ({ n })), { spread: true }]);
    $("rk-uniform").appendChild(text("div", "sub", `습관이 같은 세계는 시드 ${u.seeds.length}개, 다른 세계는 ${b.seeds.length}개 평균이다.`));
    const rob = R.robustness && R.robustness.results;
    if (rob) {
      C.table($("rk-rob"), [
        { h: "전조 신호 세기", render: (r) => `${r.k}배` },
        { h: "d1", render: (r) => f3(r.v.d1_emergency), num: true },
        { h: "d2", render: (r) => f3(r.v.d2_corrective), num: true },
        { h: "d3", render: (r) => f3(r.v.d3_corroborated), num: true },
        { h: "진짜 라벨", render: (r) => f3(r.v.truth), num: true },
        { h: "d2−d1", render: (r) => sg(r.v.d2_corrective - r.v.d1_emergency), num: true },
      ], Object.entries(rob).map(([k, v]) => ({ k, v })));
    }
    const val = R.validity.mean;
    C.hbars($("rk-valid"), [["정밀도", "precision"], ["재현율", "recall"], ["F1", "f1"], ["F2", "f2"], ["양성 비율", "positive_rate"]].map(([l, k]) => ({ label: l, value: val[k] })), { diverging: true, fmt: (v) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2), valueName: "순위 상관", label: "라벨 지표와 모형 성능의 순위 상관", max: 1 });
  }

  function renderExample() {
    const ex = S.rank.base.topk.examples[+$("rk-ex").value || 0];
    if (!ex) return;
    const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 16px;margin-top:10px";
    for (const [k, title] of [["d1_emergency", "d1 모형"], ["d2_corrective", "d2 모형"], ["d3_corroborated", "d3 모형"], ["truth", "진짜 라벨 모형"]]) {
      const col = el("div");
      col.appendChild(text("h3", "", title));
      const ul = el("ul", { class: "rlist" });
      for (const it of ex.lists[k]) {
        const li = el("li");
        const l = el("div"); l.appendChild(text("div", "nm", `${CAT[it.category] || it.category} #${it.asset}`)); l.appendChild(text("div", "zn", it.floor < 0 ? "중앙 설비" : `${it.floor}층`));
        li.appendChild(l); li.appendChild(text("div", "rs", it.failed_in_4w ? "● 고장" : "–"));
        ul.appendChild(li);
      }
      col.appendChild(ul); grid.appendChild(col);
    }
    put("rk-lists", text("div", "sub", `${ex.archetype} 사이트 ${ex.site}, ${ex.week}주를 마친 시점의 판단`), grid);
  }

  /* ------------------------------------------------------------------ 3. 현장 확인 */
  function renderAudit() {
    const A = S.audit;
    renderAuditSim();
    const ng = A.audit.n_grid, fx = (v) => String(ng[Math.round(v)] ?? "");
    const mk = (arr, name) => [{ name, color: "var(--series-1)", points: arr.map((y, i) => ({ x: i, y })), markers: true }];
    const mean = A.multi.audit || A.audit;
    C.lineChart($("au-p"), mk(mean.p_near, "최선과 0.02 이내인 비율"), { y0: 0, y1: 1, xTicks: ng.length - 1, fmtX: fx, fmtY: (v) => pc(v), height: 170, label: "정의 선택 정확도" });
    C.lineChart($("au-r"), mk(mean.regret, "잃은 점수"), { y0: 0, xTicks: ng.length - 1, fmtX: fx, fmtY: (v) => v.toFixed(3), height: 170, label: "정의 선택 후회" });
    const st = A.multi.strategies, order = ["fixed_d1_emergency", "fixed_d2_corrective", "fixed_d3_corroborated", "audit_40", "audit_80", "oracle", "truth"];
    const ko = { fixed_d1_emergency: "전 사이트 d1", fixed_d2_corrective: "전 사이트 d2", fixed_d3_corroborated: "전 사이트 d3", audit_40: "확인 40건으로 사이트별 선택", audit_80: "확인 80건으로 사이트별 선택", oracle: "사이트별 최선(정답으로 고름)", truth: "진짜 고장으로 학습(상한)" };
    const base = st.fixed_d1_emergency.truth_auc.mean;
    $("au-st-sub").textContent = "고정 d1에 비해 진짜 고장 AUC가 얼마나 올랐는지. 시드 5개 평균.";
    C.hbars($("au-strat"), order.map((k) => ({ label: ko[k], value: st[k].truth_auc.mean - base, sub: `AUC ${f3(st[k].truth_auc.mean)}` })), { fmt: (v) => "+" + v.toFixed(3), labelW: 210, valueName: "AUC 증가", label: "정의 선택 전략 비교" });
    const s = S.sum.customization;
    put("au-note", text("b", "", "사이트별 선택은 고정 d2를 넘지 못했다. "), text("span", "", `확인 80건으로 고른 모형의 AUC는 ${f3(s.audit_80)}이고 전 사이트 d2는 ${f3(s.fixed_d2)}이다. 이 시뮬레이터에서는 시정 작업지시를 모두 고장으로 보는 넓은 정의 하나가 사이트별 최선과 거의 같았다. 현장 확인은 모형을 더 낫게 하기보다 d1처럼 맞지 않는 정의를 걸러 내는 데 쓸모가 있다.`));
    const mt = A.maturity;
    C.table($("au-delay"), [
      { h: "습관", k: "a" }, { h: "중앙값(일)", render: (r) => r.v.median, num: true },
      { h: "7일 안", render: (r) => pc(r.v.within["7"]), num: true }, { h: "28일 안", render: (r) => pc(r.v.within["28"]), num: true },
    ], ARCH.map((a) => ({ a, v: mt.entry_delay_by_archetype[a] })));
    C.table($("au-mature"), [
      { h: "학습 라벨", k: "k" }, { h: "AUC", render: (r) => f3(r.v.truth_auc), num: true }, { h: "늦게 입력 사이트 AUC", render: (r) => f3(r.v.truth_auc_late_sites), num: true },
    ], Object.entries(mt.training_variants).map(([k, v]) => ({ k, v })));
  }

  function renderAuditSim() {
    const D = S.audit.demo, site = D.sites[$("au-site").value], i = +$("au-n").value, n = String(D.n_grid[i]);
    $("au-n-val").textContent = `${n}건`;
    const r = site.by_n[n];
    const rows = D.names.map((nm, k) => ({ label: DEF[nm], est: r.score[k], lo: r.lo[k], hi: r.hi[k], truth: site.truth.score[k], picked: nm === r.pick }));
    C.intervals($("au-int"), rows, { min: 0, max: 1, labelW: 190, label: "현장 확인 추정", fmt: (v) => v.toFixed(2) });
    const ok = r.pick === site.best;
    $("au-sub").textContent = `${site.archetype} 사이트. 점수는 F2(재현율에 두 배 무게). 점은 추정, 선은 90% 구간, 마름모는 정답. 고른 정의는 ${dshort(r.pick)}이고 정답 기준 최선은 ${dshort(site.best)}이다${ok ? "" : ` (점수 차이 ${(site.truth.score[D.names.indexOf(site.best)] - site.truth.score[D.names.indexOf(r.pick)]).toFixed(2)})`}.`;
  }

  /* ------------------------------------------------------------------ 품질 */
  function renderQuality() {
    const rep = S.qmode === "book" ? S.qbook : S.qraw;
    if (!rep) { put("q-kpis", text("div", "empty", "샘플 점검 결과를 불러오는 중이다")); return; }
    const t = rep.total;
    put("q-kpis",
      C.tile("작업지시", C.fmtN(t.work_orders), `사이트 ${rep.sites.length}곳, 3년`),
      C.tile("유형을 못 읽은 행", C.fmtN(t.unknown_type), pc(t.unknown_type / t.work_orders, 1), t.unknown_type ? "bad" : "good"),
      C.tile("설비 번호가 빈 행", C.fmtN(t.missing_asset), pc(t.missing_asset / t.work_orders, 1)),
      C.tile("중복·날짜 역전", C.fmtN(t.exact_duplicates + t.date_inverted), `중복 ${t.exact_duplicates}, 역전 ${t.date_inverted}`),
      C.tile("정의에 쓸 수 있는 행", pc(t.usable_share_mean, 1), "사이트 평균"));
    const hi = rep.issues.filter((i) => i.level !== "low"), low = rep.issues.filter((i) => i.level === "low");
    $("q-issues-sub").textContent = hi.length ? `심각한 문제 ${hi.length}건, 가벼운 문제 ${low.length}건` : `심각한 문제 없음. 가벼운 문제 ${low.length}건`;
    const ul = el("ul", { class: "warnlist" });
    for (const i of hi) {
      const li = el("li");
      li.appendChild(C.badge(i.level === "high" ? "fail" : "legal", i.level === "high" ? "높음" : "중간"));
      li.appendChild(document.createTextNode(` 사이트 ${i.site}: ${i.text}`));
      if (i.suggestion && Object.keys(i.suggestion).length) {
        const KO = { emergency: "긴급", corrective: "시정", preventive: "예방" };
        li.appendChild(text("div", "muted", "코드표 제안: " + Object.entries(i.suggestion).map(([c, v]) => `${c} → ${KO[v.kind] || v.kind}(${v.count}건, 확신 ${v.confidence})`).join(", ")));
      }
      ul.appendChild(li);
    }
    put("q-issues", ul);
    const e = S.qraw && S.same.quality ? S.same.quality.code_book_effect_d1 : null;
    if (e) {
      $("q-effect-sub").textContent = `사이트 ${e.sites.join(", ")}는 유형 코드가 A1, B2, C3다. 정의 d1(긴급만)을 적용한 라벨을 진짜 고장과 맞췄다.`;
      C.table($("q-effect"), [{ h: "", k: "k" }, { h: "사건", render: (r) => r.v.incidents, num: true }, { h: "정밀도", render: (r) => (r.v.precision == null ? "–" : pc(r.v.precision)), num: true }, { h: "재현율", render: (r) => pc(r.v.recall), num: true }],
        [{ k: "코드표 없음", v: e.without }, { k: "코드표 적용", v: e.with }]);
    }
    C.table($("q-table"), [
      { h: "사이트", k: "site" }, { h: "작업지시", render: (r) => C.fmtN(r.work_orders), num: true }, { h: "중복", k: "exact_duplicates", num: true }, { h: "날짜 역전", k: "date_inverted", num: true },
      { h: "설비 없음", k: "missing_asset", num: true }, { h: "유형 불명", k: "unknown_type", num: true }, { h: "긴급 비중", render: (r) => pc(r.emergency_share), num: true }, { h: "사용 가능", render: (r) => pc(r.usable_share, 1), num: true },
    ], rep.sites);
  }

  /* ------------------------------------------------------------------ 감시 */
  function renderMonitor() {
    const M = S.mon, s = S.sum.drift;
    put("mo-kpis",
      C.tile("탐지한 습관 변화", `${s.detected} / ${s.shifts}`, "정답 없이 작업지시 로그만 사용"),
      C.tile("탐지까지 걸린 시간(중앙값)", `${s.delay_median_weeks}주`, `가장 늦은 것 ${s.delay_max_weeks}주`, "bad"),
      C.tile("바뀌지 않은 사이트의 거짓 경보", `${s.false_alarm_site_runs} / ${s.quiet_site_runs}`, "사이트·실행 단위"),
      C.tile("바뀐 사이트에서 d1 F1", `${f2(s.d1_f1_before)} → ${f2(s.d1_f1_after)}`, "습관이 바뀌기 전과 후", "bad"));
    const site = $("mo-site").value, sig = $("mo-sig").value, d = M.series.sites[site], weeks = M.series.weeks;
    const sh = M.series.shifts.find(([x]) => String(x) === site);
    const vals = d.series[sig], path = d.signals[sig].path;
    const alarm = d.signals[sig].alarm_week;
    $("mo-sub").textContent = `${SIG[sig]} (4주 단위). ` + (sh ? `이 사이트는 100주에 '${sh[2]}' 습관으로 바뀐다. ` : "습관이 바뀌지 않는 사이트다. ") + (alarm != null ? `이 신호의 경보는 ${alarm}주에 났다.` : "이 신호의 경보는 없었다.");
    const x = (arr) => [{ name: SIG[sig], color: "var(--series-1)", points: weeks.map((w, i) => ({ x: w, y: arr[i] })) }];
    C.lineChart($("mo-series"), x(vals), { y0: 0, height: 170, fmtX: (v) => Math.round(v) + "주", fmtY: (v) => (sig === "np_rate" ? v.toFixed(2) : pc(v)), marker: sh ? 100 : undefined, xTicks: 6, label: SIG[sig] });
    C.lineChart($("mo-cusum"), [{ name: "CUSUM (경보 기준 " + M.h + ")", color: "var(--series-2)", points: weeks.map((w, i) => ({ x: w, y: path[i] })) }], { y0: 0, y1: Math.max(M.h * 1.3, ...path), height: 150, refY: M.h, fmtX: (v) => Math.round(v) + "주", fmtY: (v) => v.toFixed(0), marker: sh ? 100 : undefined, xTicks: 6, label: "CUSUM" });
    C.table($("mo-target"), [
      { h: "바뀐 습관", k: "t" }, { h: "탐지", render: (r) => `${r.v.detected} / ${r.v.n}`, num: true }, { h: "지연(주)", render: (r) => (r.v.delays.length ? r.v.delays.join(", ") : "–"), num: true },
    ], Object.entries(M.by_target).map(([t, v]) => ({ t, v })));
    const mean = (name, tag) => M.runs.reduce((a, r) => a + r.label_quality_shifted_sites[name][tag].f1, 0) / M.runs.length;
    C.table($("mo-label"), [
      { h: "정의", render: (r) => DEF[r.n] }, { h: "바뀌기 전 F1", render: (r) => f2(mean(r.n, "before")), num: true }, { h: "바뀐 뒤 F1", render: (r) => f2(mean(r.n, "after")), num: true },
    ], ["d1_emergency", "d2_corrective", "d3_corroborated"].map((n) => ({ n })));
  }

  /* ------------------------------------------------------------------ 내 로그 */
  function renderBring() {
    if (!S.same) return;
    if (S.schema) {
      C.table($("bring-schema"), [{ h: "열", k: "column" }, { h: "형식", k: "type" }, { h: "뜻", k: "meaning" }], S.schema.work_orders);
    }
    const up = $("bring-upload"), out = $("bring-out");
    if (!up.dataset.ready) {
      up.dataset.ready = "1";
      if (STATIC) {
        up.replaceChildren(text("div", "dropped", "정적 데모에는 서버가 없어 올릴 수 없다. 샘플 로그의 점검 결과는 '품질' 탭에서 본다. 로컬에서 `faultline serve`를 실행하면 이 화면에서 올릴 수 있다."));
      } else {
        const file = el("input", { type: "file", accept: ".csv", "aria-label": "작업지시 CSV" });
        const book = el("textarea", { rows: "3", placeholder: '코드표(선택): {"A1": "emergency", "B2": "corrective", "C3": "preventive"}', "aria-label": "코드표 JSON" });
        book.style.cssText = "font:inherit;padding:6px 8px;border:1px solid var(--axis);border-radius:6px;background:var(--surface-1);color:var(--text-primary)";
        const btn = el("button", { type: "button", class: "btn primary" }, "점검");
        const sample = el("a", { href: "/v1/sample/work_orders.csv", download: "" }, "샘플 CSV 받기");
        btn.addEventListener("click", async () => {
          if (!file.files[0]) { out.replaceChildren(text("div", "err", "CSV 파일을 고른다")); return; }
          const fd = new FormData(); fd.append("file", file.files[0]); if (book.value.trim()) fd.append("code_book", book.value);
          out.replaceChildren(text("div", "muted", "점검 중"));
          try {
            const rep = await api("/v1/quality", { method: "POST", body: fd });
            const t = rep.total;
            out.replaceChildren(text("div", "sub", `작업지시 ${C.fmtN(t.work_orders)}건, 유형 불명 ${t.unknown_type}, 설비 번호 없음 ${t.missing_asset}, 중복 ${t.exact_duplicates}, 날짜 역전 ${t.date_inverted}`),
              ...rep.issues.filter((i) => i.level !== "low").slice(0, 12).map((i) => text("div", "", `사이트 ${i.site}: ${i.text}`)));
          } catch (e) { out.replaceChildren(text("div", "err", e.message)); }
        });
        up.replaceChildren(file, book, btn, sample, text("div", "dropped", '샘플 CSV는 사이트 0, 1, 5의 로그다. 사이트 5는 유형 코드가 A1(긴급), B2(시정), C3(예방)이라 위 코드표를 넣어야 읽힌다.'));
      }
    }
    const box = $("bring-def");
    if (!box.dataset.ready && S.defs) {
      box.dataset.ready = "1";
      const ta = el("textarea", { rows: "18", "aria-label": "고장 정의 YAML", spellcheck: "false" });
      ta.style.cssText = "width:100%;font:12px/1.5 ui-monospace,Menlo,monospace;padding:8px;border:1px solid var(--axis);border-radius:8px;background:var(--surface-1);color:var(--text-primary)";
      ta.value = S.defs.template;
      const res = el("div");
      const mk = (label, train) => {
        const b = el("button", { type: "button", class: "btn" + (train ? "" : " primary") }, label);
        if (STATIC) { b.disabled = true; b.title = "정적 데모에서는 실행되지 않는다"; }
        b.addEventListener("click", async () => {
          res.replaceChildren(text("div", "muted", "계산 중"));
          try {
            const r = await api("/v1/definitions/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ yaml: ta.value, train }) });
            const rows = [{ k: "전체", v: r.overall }, ...ARCH.map((a) => ({ k: a, v: r.by_archetype[a] }))];
            const tb = el("div");
            res.replaceChildren(text("div", "sub", `사건 ${C.fmtN(r.incidents)}건. 창 단위 정밀도 ${pc(r.window.precision)}, 재현율 ${pc(r.window.recall)}` + (r.model ? `. 이 라벨로 학습한 모형의 진짜 AUC ${f3(r.model.truth_auc)} (참고: d1 ${f3(r.model.reference_truth_auc.d1_emergency)}, d2 ${f3(r.model.reference_truth_auc.d2_corrective)})` : "")), tb);
            C.table(tb, [{ h: "사이트 습관", k: "k" }, { h: "정밀도", render: (x) => pc(x.v.precision), num: true }, { h: "재현율", render: (x) => pc(x.v.recall), num: true }, { h: "F1", render: (x) => f2(x.v.f1), num: true }], rows);
          } catch (e) { res.replaceChildren(text("div", "err", e.message)); }
        });
        return b;
      };
      const row = el("div", { class: "ctrl" }); row.style.marginTop = "8px";
      row.append(mk("평가", false), mk("평가 + 모형 학습(느림)", true));
      box.replaceChildren(ta, row, res, ...(STATIC ? [text("div", "dropped", "정적 데모에서는 읽기만 된다. 정의 파일의 예는 '고장 정의' 탭의 더 자세히에 있다.")] : []));
    }
  }

  init();
})();
