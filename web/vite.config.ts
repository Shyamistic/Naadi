import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.NAADI_API_TARGET ?? "http://127.0.0.1:8000";
const targetUrl = new URL(apiTarget);
const apiBase = targetUrl.pathname === "/" ? "" : targetUrl.pathname.replace(/\/$/, "");

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: (path) => `${apiBase}${path.replace(/^\/api/, "")}` } } },
  preview: { proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: (path) => `${apiBase}${path.replace(/^\/api/, "")}` } } },
  build: { chunkSizeWarningLimit: 1100, rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"], react: ["react", "react-dom", "react-router"], aria: ["react-aria-components", "@internationalized/date"] } } } },
});
