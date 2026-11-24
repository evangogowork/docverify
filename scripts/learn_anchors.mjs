#!/usr/bin/env node
// Scan the source tree for `@learn:<id>` ... `@learn:end <id>` comment pairs and write
// frontend/src/generated/anchors.json: { id: { path, start, end } } (1-based, inclusive).
// Line numbers are never written by hand; the learn page links to
// <repo>/blob/<sha>/<path>#L<start>-L<end> using this file.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "frontend/src/generated/anchors.json");
const SKIP = new Set(["node_modules", ".venv", ".git", "dist", ".runtime", "generated", "test-results",
  "playwright-report", "videos", ".hypothesis", ".pytest_cache", "__pycache__"]);
const EXT = new Set([".py", ".ts", ".tsx", ".mjs", ".sql", ".yml", ".sh"]);
const OPEN = /@learn:(?!end\b)([a-z0-9-]+)/;
const CLOSE = /@learn:end ([a-z0-9-]+)/;

function* walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (EXT.has(path.extname(e.name)) && !p.endsWith("learn_anchors.mjs") && !p.endsWith("check_anchors.mjs")) yield p;
  }
}

export function scan() {
  const anchors = {};
  const errors = [];
  for (const file of walk(ROOT)) {
    const rel = path.relative(ROOT, file).split(path.sep).join("/");
    const lines = fs.readFileSync(file, "utf8").split("\n");
    const open = {};
    lines.forEach((line, i) => {
      let m;
      if ((m = line.match(CLOSE))) {
        const id = m[1];
        if (!(id in open)) errors.push(`${rel}:${i + 1} end without start: ${id}`);
        else { anchors[id] = { path: rel, start: open[id], end: i + 1 }; delete open[id]; }
      } else if ((m = line.match(OPEN))) {
        const id = m[1];
        if (id in anchors || id in open) errors.push(`${rel}:${i + 1} duplicate anchor: ${id}`);
        open[id] = i + 1;
      }
    });
    for (const id of Object.keys(open)) errors.push(`${rel}:${open[id]} start without end: ${id}`);
  }
  const sorted = Object.fromEntries(Object.keys(anchors).sort().map((k) => [k, anchors[k]]));
  return { anchors: sorted, errors };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { anchors, errors } = scan();
  if (errors.length) { console.error(errors.join("\n")); process.exit(1); }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(anchors, null, 2) + "\n");
  console.log(`learn_anchors: ${Object.keys(anchors).length} anchors -> ${path.relative(ROOT, OUT)}`);
}
