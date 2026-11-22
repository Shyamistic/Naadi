import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";
import { pwaPlugin } from "./pwa.config";

// A build id (commit and UTC build time), written into index.html and shown on the About page. Every build
// changes index.html, so the service worker always re-fetches it, and anyone can see which build is live.
const commit = (() => { try { return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); } catch { return "unknown"; } })();
const buildId = `${commit} ${new Date().toISOString().slice(0, 16)}Z`;
const buildIdPlugin = { name: "naadi-build-id", transformIndexHtml: (html: string) => html.replace("</head>", `  <meta name="naadi-build" content="${buildId}" />\n  </head>`) };

// Where /api is proxied in `npm run dev` and `vite preview`. The default is the live API, which is served under /api.
// For a local API started with uvicorn (served at the root), set NAADI_API_TARGET=http://127.0.0.1:8010.
const apiTarget = process.env.NAADI_API_TARGET ?? "https://13-235-147-97.sslip.io/api";
const targetUrl = new URL(apiTarget);
// The proxy goes to the origin and the rewrite adds the target's path once ("" locally, "/api" on the server).
// Putting the path in `target` as well made http-proxy prepend it a second time (/api/api/...).
const apiBase = targetUrl.pathname.replace(/\/$/, "");
const apiProxy = { "/api": { target: targetUrl.origin, changeOrigin: true, rewrite: (path: string) => `${apiBase}${path.replace(/^\/api/, "")}` } };

export default defineConfig({
  plugins: [react(), buildIdPlugin, pwaPlugin],
  define: { __NAADI_BUILD__: JSON.stringify(buildId) },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  build: { chunkSizeWarningLimit: 1100, rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"], react: ["react", "react-dom", "react-router"], aria: ["react-aria-components", "@internationalized/date"] } } } },
});
