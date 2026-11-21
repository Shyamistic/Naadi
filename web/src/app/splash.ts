// The boot splash (#splash in index.html, driven by public/boot.js) covers the whole window while Naadi starts.
// It must always end. Pages without a map hide it as soon as the shell renders. Map pages hide it when the map is
// ready, when the map can't start, or after MAP_SPLASH_CAP_MS, whichever comes first.
export const MAP_SPLASH_CAP_MS = 5000;

// Tells boot.js that the app started, so its 15-second "Naadi couldn't start" message stays hidden.
export function markAppStarted(): void {
  window.__naadiReady = true;
}

export function hideSplash(): void {
  markAppStarted();
  if (window.__naadiSplash) window.__naadiSplash.hide();
  else document.getElementById("splash")?.remove();
}
