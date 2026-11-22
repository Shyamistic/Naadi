import type maplibregl from "maplibre-gl";

// Vehicle icons for the map, drawn on a canvas so there are no image files to license or ship.
// All icons point UP; the map rotates them to the vehicle's heading (icon-rotate).

export const ICON_BUS_FRESH = "naadi-bus-fresh";
export const ICON_BUS_STALE = "naadi-bus-stale";
export const ICON_TRAIN = "naadi-train";

const SIZE = 56; // drawing size in pixels; registered with pixelRatio 2, so it shows at 28 CSS px before icon-size

function canvas(): [HTMLCanvasElement, CanvasRenderingContext2D] | null {
  const el = document.createElement("canvas");
  el.width = SIZE; el.height = SIZE;
  const ctx = el.getContext("2d");
  return ctx ? [el, ctx] : null;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// A bus seen from above: body, dark windscreen at the front (top), roof hatch and rear window.
function drawBus(body: string): ImageData | null {
  const made = canvas();
  if (!made) return null;
  const [, ctx] = made;
  ctx.clearRect(0, 0, SIZE, SIZE);
  // soft shadow
  ctx.fillStyle = "rgba(15,23,42,.22)";
  ctx.beginPath(); ctx.ellipse(SIZE / 2 + 1.5, SIZE / 2 + 2.5, 11, 24, 0, 0, Math.PI * 2); ctx.fill();
  // body
  roundRect(ctx, 17, 3, 22, 50, 7);
  ctx.fillStyle = body; ctx.fill();
  ctx.lineWidth = 2.5; ctx.strokeStyle = "#ffffff"; ctx.stroke();
  // windscreen (front)
  roundRect(ctx, 20, 7, 16, 9, 3);
  ctx.fillStyle = "rgba(15,23,42,.88)"; ctx.fill();
  // side windows as two light strips
  ctx.fillStyle = "rgba(255,255,255,.55)";
  roundRect(ctx, 20, 20, 4, 22, 2); ctx.fill();
  roundRect(ctx, 32, 20, 4, 22, 2); ctx.fill();
  // roof hatch
  roundRect(ctx, 24.5, 26, 7, 9, 2);
  ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.fill();
  // rear window
  roundRect(ctx, 21, 46, 14, 4, 2);
  ctx.fillStyle = "rgba(15,23,42,.55)"; ctx.fill();
  return ctx.getImageData(0, 0, SIZE, SIZE);
}

// Adds the icons to the map once per style. A new style (theme or language change) drops them, so callers run this
// again after every "style.load" (the overlays depend on styleVersion and do).
// A metro or Namo Bharat car seen from above: longer and narrower than a bus, with a light stripe of windows.
function drawTrain(body: string): ImageData | null {
  const made = canvas();
  if (!made) return null;
  const [, ctx] = made;
  ctx.clearRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = "rgba(15,23,42,.22)";
  ctx.beginPath(); ctx.ellipse(SIZE / 2 + 1.5, SIZE / 2 + 2.5, 9, 26, 0, 0, Math.PI * 2); ctx.fill();
  roundRect(ctx, 19, 1, 18, 54, 9);
  ctx.fillStyle = body; ctx.fill();
  ctx.lineWidth = 2.5; ctx.strokeStyle = "#ffffff"; ctx.stroke();
  roundRect(ctx, 22, 5, 12, 7, 3);
  ctx.fillStyle = "rgba(15,23,42,.88)"; ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,.6)";
  for (let y = 16; y < 50; y += 8) { roundRect(ctx, 25, y, 6, 5, 1.5); ctx.fill(); }
  return ctx.getImageData(0, 0, SIZE, SIZE);
}

export function ensureVehicleIcons(map: maplibregl.Map): void {
  const wanted: [string, () => ImageData | null][] = [[ICON_BUS_FRESH, () => drawBus("#138808")], [ICON_BUS_STALE, () => drawBus("#8b95a5")], [ICON_TRAIN, () => drawTrain("#1f4fa3")]];
  for (const [name, draw] of wanted) {
    if (map.hasImage(name)) continue;
    const image = draw();
    if (image) map.addImage(name, image, { pixelRatio: 2 });
  }
}

// Heading of travel in degrees clockwise from north (what icon-rotate expects), from two positions.
export function bearingDegrees(from: [number, number], to: [number, number]): number {
  const rad = Math.PI / 180;
  const dLon = (to[0] - from[0]) * rad;
  const lat1 = from[1] * rad; const lat2 = to[1] * rad;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (Math.atan2(y, x) / rad + 360) % 360;
}

export function metresBetween(a: [number, number], b: [number, number]): number {
  const dLat = (b[1] - a[1]) * 111320;
  const dLon = (b[0] - a[0]) * 111320 * Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180);
  return Math.hypot(dLat, dLon);
}

// Remembers each bus's last position and heading between polls. A bus that moved more than 12 m gets a new heading;
// a parked or barely moving bus keeps the last one (the live feed itself carries no heading).
const memory = new Map<string, { at: [number, number]; bearing: number }>();
export function headingFor(id: string, at: [number, number]): number {
  const prev = memory.get(id);
  let bearing = prev?.bearing ?? 0;
  if (prev && metresBetween(prev.at, at) > 12) { bearing = bearingDegrees(prev.at, at); memory.set(id, { at, bearing }); }
  else if (!prev) memory.set(id, { at, bearing });
  if (memory.size > 12000) memory.clear(); // the fleet is about 6,000; this only guards against unbounded growth
  return bearing;
}
