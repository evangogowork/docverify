import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Source links on the learn page point at an immutable commit, never at `main`.
function gitSha(): string {
  if (process.env.VITE_GIT_SHA) return process.env.VITE_GIT_SHA;
  try { return execSync("git rev-parse HEAD", { cwd: __dirname }).toString().trim(); } catch { return "main"; }
}

// Serve ../docs/videos at /videos in dev and copy it into the build, so the tutorial and the
// learn page share one set of files.
function videos(): Plugin {
  const dir = path.resolve(__dirname, "../docs/videos");
  return {
    name: "docverify-videos",
    configureServer(server) {
      server.middlewares.use("/videos", (req, res, next) => {
        const file = path.join(dir, decodeURIComponent((req.url || "/").split("?")[0]));
        if (!file.startsWith(dir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return next();
        res.setHeader("Content-Type", file.endsWith(".mp4") ? "video/mp4" : "application/octet-stream");
        fs.createReadStream(file).pipe(res);
      });
    },
    writeBundle(opts) {
      if (!fs.existsSync(dir)) return;
      const out = path.join(opts.dir || "dist", "videos");
      fs.mkdirSync(out, { recursive: true });
      const copy = (from: string, to: string) => {
        fs.mkdirSync(to, { recursive: true });
        for (const e of fs.readdirSync(from, { withFileTypes: true })) {
          if (e.isDirectory()) copy(path.join(from, e.name), path.join(to, e.name));
          else if (e.name.endsWith(".mp4")) fs.copyFileSync(path.join(from, e.name), path.join(to, e.name));
        }
      };
      copy(dir, out);
    },
  };
}

export default defineConfig({
  plugins: [react(), videos()],
  define: {
    __GIT_SHA__: JSON.stringify(gitSha()),
    __REPO_URL__: JSON.stringify(process.env.VITE_REPO_URL || "https://github.com/evangogowork/docverify"),
  },
  server: {
    port: 5501,
    fs: { allow: [".."] },   // docs/interview.md and docs/videos live outside frontend/
    proxy: {
      "/v1": "http://127.0.0.1:8501",
      "/mock": { target: "http://127.0.0.1:8511", rewrite: (p) => p.replace(/^\/mock/, "") },
    },
  },
});
