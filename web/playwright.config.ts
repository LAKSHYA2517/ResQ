import { defineConfig } from "@playwright/test";

// Specs live in ../tests/e2e (brief layout). `make e2e` sets NODE_PATH so they can import
// @playwright/test from web/node_modules.
export default defineConfig({
  testDir: "../tests/e2e",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173", viewport: { width: 1366, height: 768 } },
  webServer: [
    {
      command: "uv run uvicorn api.main:app --port 8000",
      cwd: "..",
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm dev",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
