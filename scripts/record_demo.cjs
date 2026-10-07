// 데모 GIF 녹화: `node scripts/record_demo.cjs http://localhost:8020 /tmp/demo /` 뒤 ffmpeg 로 GIF 변환 (Makefile: make demo-gif)
// 흐름: 1 같은 로그, 다른 고장 → 2 점검 순서가 바뀐다 → 3 현장 확인 표본 수
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
  await wait("#hero .tile"); await wait("#def-timeline svg");
  await pause(3400);                                        // 상단 세 칸: 정의만 바꾼 두 모형, 자기 라벨 채점, 긴급 코드를 안 쓰는 사이트
  await page.selectOption("#def-arch", "표준"); await pause(2400);       // 표준 사이트: d1도 진짜 고장을 꽤 잡는다
  await page.selectOption("#def-arch", "긴급 안 씀"); await pause(2800); // 긴급 코드를 안 쓰는 사이트: d1은 거의 못 잡는다
  await page.mouse.wheel(0, 300); await pause(2400);
  await page.mouse.wheel(0, -300);
  await tab("rank", "#rk-dumbbell svg"); await pause(3400);              // 자기 라벨 채점과 진짜 채점이 어긋난다
  await page.mouse.wheel(0, 520); await pause(2800);                     // 습관별 점검 적중
  await page.mouse.wheel(0, -520);
  await tab("audit", "#au-int svg"); await pause(2000);                  // 현장 확인 건수를 늘리며 추정이 모인다
  for (const v of ["0", "2", "4", "5"]) { await page.fill("#au-n", v); await pause(1300); }
  await page.mouse.wheel(0, 420); await pause(2600);
  const video = page.video();
  await ctx.close();
  const path = await video.path();
  await browser.close();
  console.log(path);
})().catch((e) => { console.error(e); process.exit(1); });
