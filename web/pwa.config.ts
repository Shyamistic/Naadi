import { VitePWA } from "vite-plugin-pwa";

export const pwaPlugin = VitePWA({
  // A new service worker takes over as soon as it is installed, so a deploy reaches returning visitors on their
  // next page load. With "prompt" and no update prompt in the UI, they kept the old version until every Naadi
  // tab was closed.
  registerType: "autoUpdate",
  includeAssets: ["boot.js", "favicon.svg"],
  manifest: {
    name: "Naadi",
    short_name: "Naadi",
    description: "Measured journey planning for Delhi",
    theme_color: "#1a3a8f",
    background_color: "#f6f7f9",
    display: "standalone",
    start_url: "/",
    icons: [{ src: "/favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }],
  },
  workbox: {
    navigateFallback: "/index.html",
    navigateFallbackDenylist: [/^\/api(?:\/|$)/],
    globPatterns: ["**/*.{js,css,html,svg,woff2}"],
    globIgnores: ["**/api/**"],
    cleanupOutdatedCaches: true,
  },
});
