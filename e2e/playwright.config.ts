import { defineConfig } from "@playwright/test";

// Expects the stack to be running (scripts/demo.sh): API 8501, mock platform 8511, frontend 5501.
export default defineConfig({
  testDir: ".",
  timeout: 180_000,
  expect: { timeout: 90_000 },
  use: { baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5501", headless: true, viewport: { width: 1440, height: 900 } },
  reporter: [["list"]],
  workers: 1,
});
