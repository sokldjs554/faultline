// 문서용 스크린샷 — `node scripts/screenshot_console.cjs http://localhost:8020 docs/images /` (정적 데모)
const { chromium } = require("playwright");
const { mkdirSync } = require("node:fs");

(async () => {
  const base = process.argv[2] || "http://localhost:8000", out = process.argv[3] || "docs/images", pagePath = process.argv[4] || "/console/";
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1.5, colorScheme: "light" });
  page.on("pageerror", (e) => console.error("pageerror", e.message));
  const wait = (sel, t = 90000) => page.waitForSelector(sel, { timeout: t });
  const tab = async (name, ready) => { await page.click(`nav.tabs button[data-tab="${name}"]`); await wait(ready); await page.waitForTimeout(700); };
  await page.goto(`${base}${pagePath}`, { waitUntil: "networkidle" });
  await wait("#hero .tile"); await wait("#ill-forest svg"); await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}/console.png` });
  await tab("who", "#who-policy svg");
  await page.screenshot({ path: `${out}/console-who.png`, fullPage: true });
  await page.selectOption("#scn", "hunch"); await page.waitForTimeout(500);
  await tab("trust", "#tr-verdict .badge");
  await page.screenshot({ path: `${out}/console-trust-hunch.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.selectOption("#scn", "base");
  await tab("who", "#who-policy svg");
  await page.screenshot({ path: `${out}/console-dark.png` });
  await browser.close();
  console.log("screenshots written to", out);
})().catch((e) => { console.error(e); process.exit(1); });
