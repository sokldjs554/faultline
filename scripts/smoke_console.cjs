// 콘솔 스모크: 모든 탭을 열어 보고 콘솔 오류, 페이지 오류, 4xx/5xx 가 있으면 실패한다. 스크린샷을 남긴다.
//   node scripts/smoke_console.cjs http://localhost:8020 /          /tmp/shots   (정적 데모)
//   node scripts/smoke_console.cjs http://localhost:8000 /console/  /tmp/shots   (라이브)
const { chromium } = require("playwright");
const { mkdirSync } = require("node:fs");

(async () => {
  const base = process.argv[2] || "http://localhost:8000", pagePath = process.argv[3] || "/console/", out = process.argv[4] || "/tmp/shots";
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const problems = [];
  async function run(name, viewport, scheme, fn) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1.5, colorScheme: scheme });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => problems.push(`[${name}] pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") problems.push(`[${name}] console.error: ${m.text()}`); });
    page.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("favicon")) problems.push(`[${name}] HTTP ${r.status()} ${r.url()}`); });
    await fn(page);
    await ctx.close();
  }
  const url = `${base}${pagePath}`;
  const wait = (page, sel, t = 60000) => page.waitForSelector(sel, { timeout: t });
  const READY = { define: "#def-timeline svg", rank: "#rk-dumbbell svg", audit: "#au-int svg", quality: "#q-kpis .tile", monitor: "#mo-series svg", bring: "#bring-schema table" };
  const tab = async (page, t) => { await page.click(`nav.tabs button[data-tab="${t}"]`); await wait(page, READY[t]); await page.waitForTimeout(400); };
  // "더 자세히" 접이식 영역을 모두 연다(열릴 때 차트를 다시 그린다)
  const openAll = async (page) => { await page.evaluate(() => document.querySelectorAll("details.more").forEach((d) => (d.open = true))); await page.waitForTimeout(500); };

  await run("desktop", { width: 1280, height: 900 }, "light", async (page) => {
    await page.goto(url, { waitUntil: "networkidle" });
    await wait(page, "#hero .tile");
    await wait(page, READY.define);
    await page.screenshot({ path: `${out}/01-define.png`, fullPage: true });
    for (const a of ["표준", "긴급 남용", "입력 누락", "늦게 입력", "코드 다름", "긴급 안 씀"]) { await page.selectOption("#def-arch", a); await page.waitForTimeout(150); }
    await page.selectOption("#def-range", "156");
    await page.click("#hm-prec"); await page.waitForTimeout(200);
    await openAll(page);
    await page.selectOption("#def-pick", "d1_emergency");
    for (const t of ["rank", "audit", "quality", "monitor", "bring"]) {
      await tab(page, t);
      if (t === "audit") { await page.fill("#au-n", "5"); await page.waitForTimeout(200); await page.selectOption("#au-site", "6"); await page.waitForTimeout(200); await page.fill("#au-n", "1"); }
      if (t === "quality") { await page.click("#q-book"); await page.waitForTimeout(300); }
      if (t === "monitor") { await page.selectOption("#mo-sig", "link_share"); await page.selectOption("#mo-site", "6"); await page.waitForTimeout(300); }
      if (t === "rank") { await page.selectOption("#rk-ex", "1"); await page.waitForTimeout(200); }
      await openAll(page);
      await page.screenshot({ path: `${out}/0${["rank", "audit", "quality", "monitor", "bring"].indexOf(t) + 2}-${t}.png`, fullPage: true });
    }
  });
  await run("dark", { width: 1280, height: 900 }, "dark", async (page) => {
    await page.goto(`${url}#rank`, { waitUntil: "networkidle" });
    await wait(page, READY.rank);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/07-dark-rank.png`, fullPage: true });
  });
  await run("mobile", { width: 390, height: 840 }, "light", async (page) => {
    await page.goto(url, { waitUntil: "networkidle" });
    await wait(page, "#hero .tile");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/08-mobile.png`, fullPage: true });
    for (const t of ["rank", "audit", "monitor"]) { await tab(page, t); await openAll(page); }
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (over > 4) problems.push(`[mobile] 가로 스크롤 ${over}px`);
  });
  await browser.close();
  if (problems.length) { console.error("PROBLEMS:\n" + [...new Set(problems)].join("\n")); process.exit(1); }
  console.log("smoke ok → " + out);
})().catch((e) => { console.error(e); process.exit(1); });
