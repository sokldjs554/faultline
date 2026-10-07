// 콘솔 스모크 — 모든 탭을 열어 보고 콘솔 오류·페이지 오류·4xx/5xx 가 있으면 실패한다. 스크린샷을 남긴다.
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
  const tab = async (page, t, sel) => { await page.click(`nav.tabs button[data-tab="${t}"]`); await wait(page, sel); await page.waitForTimeout(400); };
  // "더 자세히" 접이식 영역을 모두 연다 (열릴 때 차트를 다시 그린다)
  const openAll = async (page) => { await page.evaluate(() => document.querySelectorAll("details.more").forEach((d) => (d.open = true))); await page.waitForTimeout(500); };

  await run("desktop", { width: 1280, height: 900 }, "light", async (page) => {
    await page.goto(url, { waitUntil: "networkidle" });
    await wait(page, "#hero .tile");
    await wait(page, "#ill-forest svg");
    await page.screenshot({ path: `${out}/01-illusion.png`, fullPage: true });
    // 세계 전환 3개
    for (const v of ["hunch", "flat", "base"]) {
      await page.selectOption("#scn", v);
      await page.waitForTimeout(500);
      await wait(page, "#ill-forest svg");
      if (v === "hunch") await page.screenshot({ path: `${out}/01b-illusion-hunch.png`, fullPage: true });
    }
    await tab(page, "who", "#who-policy svg");
    await page.screenshot({ path: `${out}/02-who.png`, fullPage: true });
    await page.click("#sc-truth"); await page.waitForTimeout(300);
    await page.check("#who-ope"); await page.waitForTimeout(300);      // 모든 정책 + OPE
    await page.selectOption("#who-k", "4"); await page.waitForTimeout(300);
    await page.uncheck("#who-ope");
    await openAll(page);
    await wait(page, "#who-curve svg");
    await page.screenshot({ path: `${out}/02b-who-open.png`, fullPage: true });
    await tab(page, "trust", "#tr-verdict .badge");
    await page.screenshot({ path: `${out}/03-trust.png`, fullPage: true });
    await openAll(page);
    await wait(page, "#tr-overlap svg");
    await page.fill('#tr-planner input[type=number] >> nth=2', "1500"); await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/03b-trust-open.png`, fullPage: true });
    await page.selectOption("#scn", "hunch"); await page.waitForTimeout(600);
    await page.screenshot({ path: `${out}/03c-trust-hunch.png`, fullPage: true });
    await tab(page, "plan", "#plan-cols .plan-list li");
    await page.check("#plan-truth"); await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/04-plan.png`, fullPage: true });
    await tab(page, "bring", "#bring-schema table");
    await page.screenshot({ path: `${out}/05-bring.png`, fullPage: true });
  });
  await run("dark", { width: 1280, height: 900 }, "dark", async (page) => {
    await page.goto(`${url}#who`, { waitUntil: "networkidle" });
    await wait(page, "#who-policy svg");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/06-dark-who.png`, fullPage: true });
  });
  await run("mobile", { width: 390, height: 840 }, "light", async (page) => {
    await page.goto(url, { waitUntil: "networkidle" });
    await wait(page, "#hero .tile");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/07-mobile.png`, fullPage: true });
    for (const t of ["who", "plan", "trust"]) { await tab(page, t, { who: "#who-policy svg", plan: "#plan-cols .plan-list li", trust: "#tr-verdict .badge" }[t]); await openAll(page); }
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (over > 4) problems.push(`[mobile] 가로 스크롤 ${over}px`);
  });
  await browser.close();
  if (problems.length) { console.error("PROBLEMS:\n" + [...new Set(problems)].join("\n")); process.exit(1); }
  console.log("smoke ok → " + out);
})().catch((e) => { console.error(e); process.exit(1); });
