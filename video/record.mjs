// Record the learn-mode walkthrough as one webm. Each narration segment: run its action, outline the
// element it talks about, hold for the segment's duration (video/durations.json from TTS; 4s default).
// Writes video/out/learn.webm and video/timeline.json ({segments:[{id, part, startMs, narrationStartMs, durMs, mark}]}).
//   node video/record.mjs            (stack must be running: scripts/demo.sh)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.LEARN_URL || "http://127.0.0.1:5501";
const narration = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const durFile = path.join(HERE, "durations.json");
const durations = fs.existsSync(durFile) ? JSON.parse(fs.readFileSync(durFile, "utf8")) : {};
const OUT = path.join(HERE, "out");
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, recordVideo: { dir: OUT, size: { width: 1600, height: 900 } } });
const page = await ctx.newPage();
const t0 = Date.now();

// A red box (or ellipse) laid over the exact element, with a soft glow and a short pulse when it appears.
async function highlight(sel, shape = "box") {
  await page.evaluate(([s, shp]) => {
    document.querySelectorAll(".rec-mark").forEach((e) => e.remove());
    if (!s) return;
    const el = document.querySelector(s);
    if (!el) { console.warn("highlight: no element for", s); return; }
    el.scrollIntoView({ block: "center", inline: "nearest" });
    if (!document.getElementById("rec-mark-style")) {
      const st = document.createElement("style"); st.id = "rec-mark-style";
      st.textContent = `.rec-mark{position:absolute;pointer-events:none;z-index:98;border:3px solid #e5383b;border-radius:8px;
        box-shadow:0 0 0 6px rgba(229,56,59,.25);animation:recpulse .6s ease-out 1}
        .rec-mark.circle{border-radius:50%}
        @keyframes recpulse{0%{transform:scale(1.25);opacity:0}60%{transform:scale(.97);opacity:1}100%{transform:scale(1)}}`;
      document.head.appendChild(st);
    }
    const r = el.getBoundingClientRect();
    const padX = shp === "circle" ? Math.max(16, r.width * 0.3) : 4;
    const padY = shp === "circle" ? Math.max(10, r.height * 0.35) : 4;
    const m = document.createElement("div");
    m.className = "rec-mark" + (shp === "circle" ? " circle" : "");
    m.dataset.target = s;
    Object.assign(m.style, { left: `${r.left + window.scrollX - padX}px`, top: `${r.top + window.scrollY - padY}px`,
      width: `${r.width + 2 * padX}px`, height: `${r.height + 2 * padY}px` });
    document.body.appendChild(m);
  }, [sel || "", shape]);
  await page.waitForTimeout(350);   // let scrolling settle before the frame is captured
}

// Point at a control, pause, then click it (so the viewer sees what is about to be clicked).
async function pointAndClick(sel, shape = "box") {
  await page.waitForSelector(sel, { timeout: 60000 });
  await highlight(sel, shape);
  await page.waitForTimeout(900);
  await page.click(sel);
  await page.waitForTimeout(300);
}

async function caption(text) {
  await page.evaluate((t) => {
    let el = document.getElementById("rec-caption");
    if (!el) {
      el = document.createElement("div"); el.id = "rec-caption";
      Object.assign(el.style, { position: "fixed", left: "50%", bottom: "18px", transform: "translateX(-50%)", maxWidth: "1200px",
        background: "rgba(0,0,0,.78)", color: "#fff", padding: "10px 18px", borderRadius: "10px", font: "22px/1.45 'PingFang SC',sans-serif", zIndex: 99, textAlign: "center" });
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
}

async function stageDone(id, statuses = ["done", "active"]) {
  await page.waitForFunction(([i, ss]) => ss.includes(document.querySelector(`li[data-stage="${i}"]`)?.dataset.status || ""), [id, statuses], { timeout: 120000 });
}

const actions = {
  async open_learn() { await page.goto(`${BASE}/learn`); await page.waitForSelector("#learn-timeline"); },
  async noop() {},
  async submit(scenario) { await page.selectOption("#learn-scenario", scenario); await pointAndClick("#learn-submit"); await stageDone("upload", ["done"]); },
  async stage(id) { await stageDone(id); await pointAndClick(`li[data-stage="${id}"]`); },
  async wait_stage(id) { await stageDone(id, ["done"]); await pointAndClick(`li[data-stage="${id}"]`); },
  async click(sel) { await pointAndClick(sel); },
  async expand(sel) { await pointAndClick(`${sel} > summary`); },
  async panel(sel) { await page.locator(sel).scrollIntoViewIfNeeded(); },
  async show_source(anchor) {
    const sel = `a[data-anchor="${anchor}"]`;
    await page.waitForSelector(sel);
    await highlight(sel);
    await page.waitForTimeout(700);
    const href = await page.locator(sel).first().getAttribute("href");
    await page.evaluate((h) => { const c = document.getElementById("rec-caption"); if (c) c.dataset.link = h; }, href);
    await caption(`看源码 → ${href}`);
    await page.waitForTimeout(1500);
  },
  async replay() { await pointAndClick("#learn-replay"); },
  async wait_replay() { await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="receipt-outcome"]')].some((e) => e.textContent === "dedup:done"), null, { timeout: 60000 }); },
  async approve() { await stageDone("review", ["active"]); await pointAndClick("#learn-approve"); },
  async open_eval() { await pointAndClick("#learn-eval"); await page.waitForSelector("#panel-eval table"); },
  async interview() { await pointAndClick("#tab-interview"); await pointAndClick("details.qa summary"); },
  async problems() { await page.goto(`${BASE}/learn`); await pointAndClick("#tab-problems"); await pointAndClick("details.problem summary"); },
};

const timeline = [];
for (const seg of narration) {
  const [name, arg] = (seg.action || "noop").split(/:(.*)/s);
  const start = Date.now() - t0;
  await actions[name](arg);
  if (!["show_source"].includes(name)) await caption(seg.text);
  await highlight(seg.highlight, seg.shape || "box");
  const hold = (durations[seg.id] ?? 4) * 1000;
  const spent = Date.now() - t0 - start;
  // The narration for this segment starts when its action has finished (so speech never runs ahead of the page).
  const mark = await page.evaluate(() => { const m = document.querySelector(".rec-mark"); return m ? { target: m.dataset.target, ...m.getBoundingClientRect().toJSON() } : null; });
  // startMs: when this segment's action begins (cut parts here). narrationStartMs: when its audio should start,
  // i.e. after the clicks/expands finished, so speech never runs ahead of the page.
  timeline.push({ id: seg.id, part: seg.part, startMs: start, narrationStartMs: start + spent, actionMs: spent, durMs: hold, mark });
  await page.waitForTimeout(hold);
  await caption("");
}
const file = await page.video().path();
await ctx.close();
await browser.close();
fs.renameSync(file, path.join(OUT, "learn.webm"));
fs.writeFileSync(path.join(HERE, "timeline.json"), JSON.stringify({ video: "video/out/learn.webm", segments: timeline }, null, 2) + "\n");
console.log(`recorded ${timeline.length} segments, ${((Date.now() - t0) / 1000).toFixed(1)}s -> video/out/learn.webm`);
