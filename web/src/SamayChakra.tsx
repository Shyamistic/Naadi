// SamayChakra: the Ashoka Chakra's 24 spokes as the 24 hours of the day. Spoke length = trip time at that hour.
type Props = { values: (number | null)[]; current: number; lang: "en" | "hi"; size?: number };

const colour = (f: number) => {
  // green (quick) -> white -> saffron (slow)
  const a = [19, 136, 8], b = [245, 245, 245], c = [255, 153, 51];
  const [p, q, u] = f < 0.5 ? [a, b, f * 2] : [b, c, (f - 0.5) * 2];
  return `rgb(${p.map((x, i) => Math.round(x + (q[i] - x) * u)).join(",")})`;
};

export default function SamayChakra({ values, current, lang, size = 220 }: Props) {
  const vals = values.filter((v): v is number => v != null);
  if (!vals.length) return null;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const R = size / 2, r0 = R * 0.2, r1 = R * 0.86;
  const best = values.indexOf(lo);
  return (
    <figure className="chakra">
      <svg width={size} height={size} viewBox={`${-R} ${-R} ${size} ${size}`} role="img"
        aria-label={lang === "hi" ? "हर घंटे यात्रा समय" : "Trip time at every hour of the day"}>
        <circle r={r1 + 6} className="chakra-rim" />
        <circle r={r0 * 0.7} className="chakra-hub" />
        {values.map((v, h) => {
          const ang = (h / 24) * 2 * Math.PI - Math.PI / 2;
          const f = v == null ? 0 : hi > lo ? (v - lo) / (hi - lo) : 0.5;
          const len = v == null ? r0 : r0 + (r1 - r0) * (0.25 + 0.75 * f);
          const x = Math.cos(ang), y = Math.sin(ang);
          return (
            <g key={h}>
              <line x1={x * r0} y1={y * r0} x2={x * len} y2={y * len} stroke={v == null ? "#2a3260" : colour(f)}
                strokeWidth={h === current ? 7 : 4.5} strokeLinecap="round" opacity={v == null ? 0.5 : 1}>
                <title>{`${String(h).padStart(2, "0")}:00 — ${v == null ? (lang === "hi" ? "सेवा नहीं" : "no service") : `${Math.round(v)} min`}`}</title>
              </line>
              {h % 3 === 0 && <text x={x * (r1 + 16)} y={y * (r1 + 16) + 4} className="chakra-h">{h}</text>}
            </g>
          );
        })}
        <text y={-4} className="chakra-big">{Math.round(values[current] ?? lo)}</text>
        <text y={14} className="chakra-small">{lang === "hi" ? "मिनट अभी" : "min now"}</text>
      </svg>
      <figcaption>
        {lang === "hi"
          ? `सबसे जल्दी ${String(best).padStart(2, "0")}:00 बजे (${Math.round(lo)} मिनट), सबसे धीमा ${Math.round(hi)} मिनट`
          : `Quickest at ${String(best).padStart(2, "0")}:00 (${Math.round(lo)} min); slowest ${Math.round(hi)} min`}
      </figcaption>
    </figure>
  );
}
