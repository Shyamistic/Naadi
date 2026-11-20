import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { pwaPlugin } from "./pwa.config";

const apiTarget = process.env.NAADI_API_TARGET ?? "https://13-235-147-97.sslip.io";
const targetUrl = new URL(apiTarget);
const apiBase = targetUrl.pathname === "/" ? "" : targetUrl.pathname.replace(/\/$/, "");
const proxyPath = (path: string) => `${apiBase}${path.replace(/^\/api/, "")}`;

export default defineConfig({
  plugins: [react(), pwaPlugin],
  server: { proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: proxyPath } } },
  preview: { proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: proxyPath } } },
  build: { chunkSizeWarningLimit: 1100, rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"], react: ["react", "react-dom", "react-router"], aria: ["react-aria-components", "@internationalized/date"] } } } },
});
