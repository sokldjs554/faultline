// 데모 GIF 녹화 — `node scripts/record_demo.cjs http://localhost:8020 /tmp/demo /` 뒤 ffmpeg 로 GIF 변환 (Makefile: make demo-gif)
// 흐름: 1 착시(로그 vs 보정) → 2 점검 대상 고르기(위험순 vs 효과순) → 3 감사(함정 세계에서 빨강)
const { chromium } = require("playwright");
const { mkdirSync } = require("node:fs");

(async () => {
  const base = process.argv[2] || "http://localhost:8000";
  const out = process.argv[3] || "/tmp/demo";
  const pagePath = process.argv[4] || "/console/";
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: out, size: { width: 1280, height: 800 } }, colorScheme: "light" });
  const page = await ctx.newPage();
  const pause = (ms) => page.waitForTimeout(ms);
  const wait = (sel, t = 90000) => page.waitForSelector(sel, { timeout: t });
  const tab = async (name, ready) => { await page.click(`nav.tabs button[data-tab="${name}"]`); await wait(ready); await pause(500); };

  await page.goto(`${base}${pagePath}`, { waitUntil: "networkidle" });
  await wait("#hero .tile"); await wait("#ill-forest svg");
  await pause(3400);                                   // 상단 세 칸: 로그만 보면 → 걷어내면 → 효과 기준 배분
  await page.mouse.wheel(0, 360); await pause(2800);   // 왜 거꾸로: 위험할수록 점검도 고장도 많다
  await page.mouse.wheel(0, -360);
  await tab("who", "#who-policy svg"); await pause(3200);        // 점검 100번당 막는 고장
  await page.mouse.wheel(0, 260); await pause(1600);
  await page.click("#sc-truth"); await pause(1800);              // 산점도: 정답 효과로 전환
  await page.mouse.wheel(0, -260);
  await page.selectOption("#scn", "hunch"); await pause(1200);   // 함정 세계로 바꾸고
  await tab("trust", "#tr-verdict .badge"); await pause(3600);   // 감사가 빨강
  await page.mouse.wheel(0, 320); await pause(2400);             // 숨은 교란이 강해질 때 감사가 잡나
  const video = page.video();
  await ctx.close();
  const path = await video.path();
  await browser.close();
  console.log(path);
})().catch((e) => { console.error(e); process.exit(1); });
