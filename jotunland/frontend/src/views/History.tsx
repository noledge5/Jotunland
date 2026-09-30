import { useMemo, useState } from "react";
import { Car, Droplets, History as HistoryIcon, ListOrdered, RefreshCw } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Badge, Card, Chips, Empty } from "../components/ui";
import { DayStrip, StripScale, runSummary } from "../components/Timeline";
import { fmtPower, fmtState, name } from "../format";
import {
  CATEGORY_LABEL,
  DAY,
  fmtClock,
  fmtDay,
  fmtDuration,
  startOfDay,
  stateText,
  toRows,
  useLogbook,
  useRuns,
  type Category,
  type EventRow,
  type Run,
} from "../history";

const RANGES = [
  { value: "heute", label: "Heute" },
  { value: "gestern", label: "Seit gestern" },
  { value: "woche", label: "7 Tage" },
];

function rangeStart(range: string): number {
  const today = startOfDay(Date.now());
  return range === "heute" ? today : range === "gestern" ? today - DAY : today - 6 * DAY;
}

const DEVICES: { slot: string; label: string; icon: LucideIcon; tone: string; category: Category }[] = [
  { slot: "acthor.power", label: "Warmwasser · AC THOR", icon: Droplets, tone: "water", category: "warmwasser" },
  { slot: "wallbox.power", label: "Wallbox", icon: Car, tone: "bolt", category: "wallbox" },
];

const TONE: Record<Category, string> = { warmwasser: "water", wallbox: "bolt", batterie: "battery", heizung: "fire", automation: "accent", sonstiges: "muted" };

function RunList({ runs }: { runs: Run[] }) {
  const [all, setAll] = useState(false);
  const shown = [...runs].reverse().slice(0, all ? undefined : 6);
  return (
    <>
      <ul className="rows compact runs">
        {shown.map((r) => (
          <li key={r.start}>
            <div className="row-text">
              <strong>
                {fmtDay(r.start)}, {fmtClock(r.start)}–{r.ongoing ? "jetzt" : fmtClock(r.end)}
                {r.ongoing && <Badge tone="warn">läuft</Badge>}
              </strong>
              <small>
                {fmtDuration(r.end - r.start)} · {r.kwh.toFixed(1).replace(".", ",")} kWh · Ø {fmtPower(r.avgW)} · max {fmtPower(r.maxW)}
              </small>
            </div>
          </li>
        ))}
      </ul>
      {runs.length > 6 && (
        <button type="button" className="link" onClick={() => setAll(!all)}>
          {all ? "weniger" : `alle ${runs.length} Läufe`}
        </button>
      )}
    </>
  );
}

function EventList({ rows }: { rows: EventRow[] }) {
  const [limit, setLimit] = useState(60);
  if (!rows.length) return <Empty>Keine Einträge in diesem Zeitraum.</Empty>;
  let lastDay = "";
  return (
    <>
      <ul className="events">
        {rows.slice(0, limit).map((r) => {
          const day = fmtDay(r.last);
          const heading = day !== lastDay ? day : null;
          lastDay = day;
          return [
            heading && <li key={`h-${heading}`} className="events-day">{heading}</li>,
            <li key={`${r.key}-${r.first}`} className={`event ${r.decision ? "decision" : ""}`} data-tone={TONE[r.category]}>
              <span className="event-time">
                {r.count > 1 ? `${fmtClock(r.first)}–${fmtClock(r.last)}` : fmtClock(r.last)}
              </span>
              <span className="event-dot" />
              <div className="event-body">
                <div className="event-title">
                  <strong>{r.title}</strong>
                  {r.count > 1 && <Badge tone="muted">{r.count}×</Badge>}
                  {r.manual && <Badge tone="info">von Hand</Badge>}
                  {r.decision && <Badge tone="ok">Entscheidung</Badge>}
                </div>
                {r.text && <span className="event-text">{r.text}</span>}
                {r.cause && !r.manual && <span className="event-cause">{r.cause}</span>}
              </div>
            </li>,
          ];
        })}
      </ul>
      {rows.length > limit && (
        <button type="button" className="link" onClick={() => setLimit(limit + 100)}>
          ältere Einträge ({rows.length - limit})
        </button>
      )}
    </>
  );
}

export function History() {
  const { mapping, entities } = useHass();
  const [range, setRange] = useState("heute");
  const [category, setCategory] = useState<"alle" | Category>("alle");
  const from = useMemo(() => rangeStart(range), [range]);

  const devices = DEVICES.filter((d) => mapping[d.slot]);
  const { runs, loading: runsLoading, error: runsError, reload: reloadRuns } = useRuns(devices.map((d) => mapping[d.slot]), from);
  const { entries, loading, error, reload } = useLogbook(from);

  // Personen → Namen, damit "von Hand" zeigt, wer es war
  const userNames = useMemo(() => {
    const out: Record<string, string> = {};
    for (const e of Object.values(entities)) {
      if (e.entity_id.startsWith("person.") && e.attributes.user_id) out[String(e.attributes.user_id)] = name(e);
    }
    return out;
  }, [entities]);

  // Zugeordnete Geräte sicher der richtigen Kategorie zuweisen
  const extra = useMemo(() => {
    const out: Record<string, Category> = {};
    for (const [slot, id] of Object.entries(mapping)) {
      if (!id) continue;
      if (slot.startsWith("acthor.")) out[id] = "warmwasser";
      else if (slot.startsWith("wallbox.")) out[id] = "wallbox";
      else if (slot.startsWith("energy.battery")) out[id] = "batterie";
      else if (slot.startsWith("pellet.")) out[id] = "heizung";
    }
    return out;
  }, [mapping]);

  const rows = useMemo(
    () =>
      toRows(entries, (id) => name(entities[id], id), userNames, extra, (id, st) => {
        const e = entities[id];
        return e ? fmtState({ ...e, state: st }) : stateText(st);
      }),
    [entries, entities, userNames, extra],
  );
  const counts = useMemo(() => {
    const c: Partial<Record<Category, number>> = {};
    for (const r of rows) c[r.category] = (c[r.category] ?? 0) + 1;
    return c;
  }, [rows]);
  const shownRows = rows.filter((r) => (category === "alle" ? r.category !== "sonstiges" : r.category === category));
  const shownDevices = devices.filter((d) => category === "alle" || d.category === category);

  const days: number[] = [];
  for (let d = startOfDay(Date.now()); d >= from; d -= DAY) days.push(d);

  const categories: ("alle" | Category)[] = ["alle", "warmwasser", "wallbox", "batterie", "heizung", "automation", "sonstiges"];

  return (
    <div className="view">
      <header className="view-head">
        <h1>Verlauf</h1>
        <div className="toolbar-right">
          <Chips value={range} onChange={setRange} options={RANGES} />
          <button type="button" className="icon-btn" aria-label="Aktualisieren" title="Aktualisieren" onClick={() => (reload(), reloadRuns())}>
            <RefreshCw size={16} className={loading || runsLoading ? "spin" : ""} />
          </button>
        </div>
      </header>

      <Chips
        value={category}
        onChange={(v) => setCategory(v as "alle" | Category)}
        options={categories
          .filter((c) => c === "alle" || counts[c] || devices.some((d) => d.category === c))
          .map((c) => ({ value: c, label: c === "alle" ? "Alle" : `${CATEGORY_LABEL[c]}${counts[c] ? ` · ${counts[c]}` : ""}` }))}
      />

      {shownDevices.length > 0 && (
        <div className="grid">
          {shownDevices.map((d) => {
            const id = mapping[d.slot]!;
            const list = runs[id] ?? [];
            return (
              <Card key={d.slot} title={d.label} icon={d.icon} tone={d.tone as "water" | "bolt"} className={devices.length === 1 ? "span-2" : ""}>
                <p className="lead">
                  <span>{runSummary(list)}</span>
                </p>
                <div className="strips">
                  {days.map((day) => (
                    <DayStrip key={day} runs={list} day={day} tone={d.tone} label={days.length > 1 ? fmtDay(day) : undefined} />
                  ))}
                  <StripScale withLabel={days.length > 1} />
                </div>
                {list.length > 0 && <RunList runs={list} />}
                {runsError && <p className="hint bad">{runsError}</p>}
              </Card>
            );
          })}
        </div>
      )}

      <Card title="Ereignisse" icon={category === "alle" ? HistoryIcon : ListOrdered}>
        <p className="hint">
          Was wann passiert ist: Automationen, Entscheidungen deiner Regelungen („Jotunland …“), Schaltvorgänge und was von Hand geändert wurde.
          Wiederkehrende Einträge sind zusammengefasst.
        </p>
        {error ? <p className="hint bad">{error}</p> : <EventList rows={shownRows} />}
      </Card>
    </div>
  );
}
