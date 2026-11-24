#!/usr/bin/env node
// CI guard for the learn page's source links:
//  1. the committed anchors.json equals a fresh scan (not stale),
//  2. every anchor id the frontend references exists,
//  3. each anchor's start/end line really carries its marker.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { scan } from "./learn_anchors.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FILE = path.join(ROOT, "frontend/src/generated/anchors.json");
const problems = [];
const { anchors, errors } = scan();
problems.push(...errors);
const committed = fs.existsSync(FILE) ? JSON.parse(fs.readFileSync(FILE, "utf8")) : {};
if (JSON.stringify(committed) !== JSON.stringify(anchors)) {
  problems.push("anchors.json is stale: run `node scripts/learn_anchors.mjs` and commit it");
}
const used = new Set();
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
  const p = path.join(d, e.name);
  if (e.isDirectory() && e.name !== "generated") walk(p);
  else if (/\.(tsx?|json)$/.test(e.name) && !p.includes("generated")) {
    const text = fs.readFileSync(p, "utf8");
    for (const m of text.matchAll(/(?:code\(|"anchor":\s*|anchor:\s*)["']([a-z0-9-]+)["']/g)) used.add(m[1]);
    // arrays: anchors: ["a", "b"] in stages.ts, <Sources ids={["a", "b"]} /> in pages
    for (const m of text.matchAll(/(?:anchors:\s*|ids=\{)\[([^\]]*)\]/g)) for (const q of m[1].matchAll(/["']([a-z0-9-]+)["']/g)) used.add(q[1]);
  }
});
walk(path.join(ROOT, "frontend/src"));
// the problems tab links the anchors named in video/problems.src.json
for (const p of JSON.parse(fs.readFileSync(path.join(ROOT, "video/problems.src.json"), "utf8")))
  for (const f of [p.code_from, p.before_from]) if (f) used.add(f.anchor);
for (const id of used) if (!(id in anchors)) problems.push(`frontend references unknown anchor: ${id}`);
for (const [id, a] of Object.entries(anchors)) {
  const lines = fs.readFileSync(path.join(ROOT, a.path), "utf8").split("\n");
  if (!lines[a.start - 1]?.includes(`@learn:${id}`)) problems.push(`${id}: start line ${a.start} lost its marker`);
  if (!lines[a.end - 1]?.includes(`@learn:end ${id}`)) problems.push(`${id}: end line ${a.end} lost its marker`);
}
if (problems.length) { console.error("check_anchors FAILED\n" + problems.join("\n")); process.exit(1); }
console.log(`check_anchors ok: ${Object.keys(anchors).length} anchors, ${used.size} referenced by the frontend`);
