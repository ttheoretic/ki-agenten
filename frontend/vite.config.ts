import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Standard-Build: Control-Center für das FastAPI-Backend (dist/).
// `vite build --mode preview`: Abspielversion einer Aufzeichnung ohne Backend (dist-preview/, relative Pfade).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "preview" ? "./" : "/",
  define: { __REPLAY__: JSON.stringify(mode === "preview") },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: mode === "preview" ? "dist-preview" : "dist", sourcemap: false },
  test: { environment: "jsdom", globals: true, include: ["tests/**/*.test.ts"] },
}));
