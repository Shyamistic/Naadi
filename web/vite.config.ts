import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api is proxied to a local API (uvicorn naadi.api:app --port 8000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
  build: { chunkSizeWarningLimit: 2500 },
});
