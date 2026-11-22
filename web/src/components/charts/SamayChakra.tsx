import { useState } from "react";
import { useT } from "../../i18n/I18nProvider";
import "./chakra.css";

// SamayChakra: the Ashoka Chakra's 24 spokes are the 24 hours of the day. Each spoke is this journey's time if you
// left at that hour. Hover, focus or tap a spoke to compare that hour with your trip; "Plan for ..." re-plans at it.
type Props = {
  values: (number | null)[];
  total: number;
  depart: number;           // hour of the planned departure (0-23)
  quiet?: number | null;    // the quietest hour
  onPickHour?: (hour: number) => void;
};

const SIZE = 260;
const CENTRE = SIZE / 2;
const RADIUS = 100;
const INNER = 36;
const pad = (n: number) => String(n).padStart(2, "0");
const polar = (hour: number, r: number) => { const a = (hour / 24) * Math.PI * 2 - Math.PI / 2; return [CENTRE + Math.cos(a) * r, CENTRE + Math.sin(a) * r] as const; };

export function SamayChakra({ values, total, depart, quiet, onPickHour }: Props) {
  const { t } = useT();
  const [active, setActive] = useState<number | null>(null);
  const valid = values.filter((v): v is number => v != null);
  if (!valid.length) return null;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const shown = active ?? depart;
  const shownValue = values[shown];
  const diff = shownValue == null ? null : Math.round(shownValue) - Math.round(total);
  const verdict = diff == null ? t("chakra.noService") : diff === 0 ? t("chakra.same") : diff < 0 ? t("chakra.faster", { min: Math.abs(diff) }) : t("chakra.slower", { min: diff });
  const tone = diff == null ? "none" : diff < 0 ? "good" : diff > 0 ? "bad" : "same";
  return <div className="chakra" data-testid="samay-chakra">
    <svg className="samay-chakra chakra-dial" viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label={`Typical journey time by hour. This trip ${Math.round(total)} minutes`} onMouseLeave={() => setActive(null)}>
      <circle className="chakra-ring" cx={CENTRE} cy={CENTRE} r={RADIUS + 4} />
      {values.map((value, hour) => {
        const fraction = value == null || max === min ? 0.35 : (value - min) / (max - min);
        const outer = INNER + (RADIUS - INNER) * (0.25 + 0.75 * fraction);
        const [x1, y1] = polar(hour, INNER);
        const [x2, y2] = polar(hour, outer);
        const [hx1, hy1] = polar(hour, INNER - 4);
        const [hx2, hy2] = polar(hour, RADIUS + 6);
        const classes = ["chakra-spoke", value == null ? "none" : "", hour === depart ? "is-trip" : "", hour === active ? "is-active" : "", hour === quiet ? "is-quiet" : ""].filter(Boolean).join(" ");
        const label = `${pad(hour)}:30, ${value == null ? t("chakra.noService") : `${Math.round(value)} min`}`;
        return <g key={hour} className="chakra-hit" role="button" tabIndex={0} aria-label={label} aria-pressed={hour === active}
          onMouseEnter={() => setActive(hour)} onFocus={() => setActive(hour)} onBlur={() => setActive(null)} onClick={() => setActive(hour)}
          onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setActive(hour); } }}>
          <line className="chakra-hitline" x1={hx1} y1={hy1} x2={hx2} y2={hy2} />
          <line className={classes} x1={x1} y1={y1} x2={x2} y2={y2} pathLength={1} style={{ animationDelay: `${hour * 22}ms` }} />
        </g>;
      })}
      <circle className="chakra-hub" cx={CENTRE} cy={CENTRE} r={INNER - 7} />
      {[0, 3, 6, 9, 12, 15, 18, 21].map((hour) => { const [x, y] = polar(hour, RADIUS + 16); return <text key={hour} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="chakra-label">{pad(hour)}</text>; })}
      {quiet != null && (() => { const [x, y] = polar(quiet, RADIUS + 4); return <circle className="chakra-quiet" cx={x} cy={y} r={5} />; })()}
      <text x={CENTRE} y={CENTRE - 2} textAnchor="middle" className="chakra-total">{shownValue == null ? "—" : Math.round(shownValue)}</text>
      <text x={CENTRE} y={CENTRE + 13} textAnchor="middle" className="chakra-unit">{active == null ? t("chakra.unit") : `${pad(shown)}:30`}</text>
    </svg>
    <div className="chakra-readout" aria-live="polite">
      <p className={`chakra-verdict ${tone}`} data-testid="chakra-verdict">{active == null ? t("chakra.hint") : `${pad(shown)}:30 · ${verdict}`}{active != null && active === quiet ? ` · ${t("chakra.quiet")}` : ""}</p>
      {onPickHour && active != null && active !== depart && shownValue != null && <button type="button" className="ui-button primary sm" data-testid="chakra-plan" onClick={() => onPickHour(active)}>{t("chakra.plan", { time: `${pad(active)}:30` })}</button>}
    </div>
  </div>;
}
