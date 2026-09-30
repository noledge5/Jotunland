import { DAY, fmtClock, fmtDuration, type Run } from "../history";
import { fmtPower } from "../format";

/** 24-Stunden-Streifen eines Tages mit den Läufen als farbige Abschnitte */
export function DayStrip({ runs, day, tone, label }: { runs: Run[]; day: number; tone: string; label?: string }) {
  const end = day + DAY;
  const inDay = runs.filter((r) => r.end > day && r.start < end);
  const now = Date.now();
  const peak = Math.max(1, ...runs.map((r) => r.maxW));
  return (
    <div className="strip-row">
      {label && <span className="strip-label">{label}</span>}
      <div className="strip" data-tone={tone}>
        {[6, 12, 18].map((h) => (
          <span key={h} className="strip-tick" style={{ left: `${(h / 24) * 100}%` }} />
        ))}
        {now > day && now < end && <span className="strip-now" style={{ left: `${((now - day) / DAY) * 100}%` }} />}
        {inDay.map((r) => {
          const a = Math.max(r.start, day);
          const b = Math.min(r.end, end);
          return (
            <span
              key={r.start}
              className="strip-run"
              title={`${fmtClock(r.start)}–${r.ongoing ? "jetzt" : fmtClock(r.end)} · ${fmtDuration(r.end - r.start)} · ${r.kwh.toFixed(1).replace(".", ",")} kWh · Ø ${fmtPower(r.avgW)}`}
              style={{ left: `${((a - day) / DAY) * 100}%`, width: `max(3px, ${((b - a) / DAY) * 100}%)`, opacity: 0.45 + 0.55 * (r.avgW / peak) }}
            />
          );
        })}
      </div>
    </div>
  );
}

export function StripScale({ withLabel = false }: { withLabel?: boolean }) {
  return (
    <div className="strip-row scale">
      {withLabel && <span className="strip-label" />}
      <div className="strip-scale">
        {["0", "6", "12", "18", "24 Uhr"].map((t, i) => (
          <span key={t} style={{ left: `${i * 25}%` }}>{t}</span>
        ))}
      </div>
    </div>
  );
}

export function runSummary(runs: Run[]): string {
  if (!runs.length) return "nicht gelaufen";
  const ms = runs.reduce((s, r) => s + (r.end - r.start), 0);
  const kwh = runs.reduce((s, r) => s + r.kwh, 0);
  return `${runs.length} ${runs.length === 1 ? "Lauf" : "Läufe"} · ${fmtDuration(ms)} · ${kwh.toFixed(1).replace(".", ",")} kWh`;
}
