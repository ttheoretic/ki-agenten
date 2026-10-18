import { defineConfig } from "@playwright/test";

// End-to-End-Test gegen das echte Backend im Dry-Run (frisches Datenverzeichnis, keine API-Kosten).
const PORT = 8799;
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1600, height: 1000 },
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: {
    command: `rm -rf ../data/e2e && AICO_OWNER_TOKEN=e2e-token-1234567890 ../.venv/bin/aicompany --mode dry_run --data-dir ../data/e2e serve --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
