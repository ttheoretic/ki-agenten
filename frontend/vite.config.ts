import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-Server leitet /api an das FastAPI-Backend weiter (aicompany serve, Port 8765)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", globals: true, include: ["tests/**/*.test.ts"] },
});
