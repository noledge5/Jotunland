import { useCallback, useEffect, useRef, useState } from "react";
import { useHass } from "./ha/HassContext";
import { norm } from "./discovery";

/* ------------------------------------------------------------------------- *
 * Verlauf: Läufe (wann lief ein Gerät, wie lange, wie viel Energie) aus dem
 * Leistungsverlauf und Ereignisse aus dem Logbuch von Home Assistant.
 * ------------------------------------------------------------------------- */

export interface Run {
  start: number; // ms
  end: number; // ms
  ongoing: boolean;
  kwh: number;
  avgW: number;
  maxW: number;
}

type HistoryPoint = { s: string; lu: number; lc?: number };
type HistoryResult = Record<string, HistoryPoint[]>;

export const DAY = 86_400_000;

export function startOfDay(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/**
 * Läufe aus einem Leistungsverlauf. Ein Wert gilt bis zur nächsten Änderung.
 * Kurze Pausen (z. B. Regelung fährt kurz auf 0) werden zu einem Lauf zusammengefasst.
 */
export function computeRuns(points: { t: number; w: number }[], until: number, thresholdW = 30, mergeGapMs = 3 * 60_000): Run[] {
  type Open = Run & { ws: number; dur: number };
  const runs: Open[] = [];
  let cur: Open | null = null;
  for (let i = 0; i < points.length; i++) {
    const { t, w } = points[i];
    const next = i + 1 < points.length ? points[i + 1].t : until;
    const dt = Math.max(0, next - t);
    if (w > thresholdW) {
      if (cur && t - cur.end <= mergeGapMs) {
        cur.end = next;
      } else {
        if (cur) runs.push(cur);
        cur = { start: t, end: next, ongoing: false, kwh: 0, avgW: 0, maxW: 0, ws: 0, dur: 0 };
      }
      cur.ws += (w * dt) / 1000;
      cur.dur += dt;
      cur.maxW = Math.max(cur.maxW, w);
    }
  }
  if (cur) runs.push(cur);
  return runs.map(({ ws, dur, ...r }) => ({
    ...r,
    kwh: ws / 3.6e6,
    avgW: dur > 0 ? (ws * 1000) / dur : 0,
    ongoing: r.end >= until - 1000 && (points[points.length - 1]?.w ?? 0) > thresholdW,
  }));
}

export function fmtDuration(ms: number): string {
  const min = Math.round(ms / 60_000);
  if (min < 1) return "< 1 min";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  return `${h} h ${String(min % 60).padStart(2, "0")} min`;
}

export function fmtClock(ms: number): string {
  return new Date(ms).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function fmtDay(ms: number): string {
  const today = startOfDay(Date.now());
  const day = startOfDay(ms);
  if (day === today) return "Heute";
  if (day === today - DAY) return "Gestern";
  return new Date(ms).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
}

/** Läufe mehrerer Leistungssensoren ab `from`. Aktualisiert sich jede Minute. */
export function useRuns(entityIds: (string | undefined)[], from: number, thresholdW = 30) {
  const { ws, entities, status } = useHass();
  // Einheiten (W/kW) aktuell lesen, ohne bei jeder Zustandsänderung neu zu laden
  const entitiesRef = useRef(entities);
  entitiesRef.current = entities;
  const ids = entityIds.filter((x): x is string => !!x);
  const key = ids.join(",");
  const [runs, setRuns] = useState<Record<string, Run[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    if (!ids.length || status !== "connected") return;
    setLoading(true);
    setError(undefined);
    try {
      const now = Date.now();
      const res = await ws<HistoryResult>({
        type: "history/history_during_period",
        start_time: new Date(from).toISOString(),
        end_time: new Date(now).toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      const out: Record<string, Run[]> = {};
      for (const id of ids) {
        const unit = String(entitiesRef.current[id]?.attributes.unit_of_measurement ?? "W");
        const factor = unit === "kW" ? 1000 : unit === "MW" ? 1e6 : 1;
        const points = (res[id] ?? [])
          .map((p) => ({ t: Math.max(from, (p.lc ?? p.lu) * 1000), w: Number(p.s) * factor }))
          .map((p) => ({ ...p, w: isFinite(p.w) ? p.w : 0 }));
        out[id] = computeRuns(points, now, thresholdW);
      }
      setRuns(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verlauf nicht lesbar");
    } finally {
      setLoading(false);
    }
  }, [key, from, thresholdW, status, ws]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return { runs, loading, error, reload: load };
}

/* --------------------------------------------------------- Ereignisse ---- */

export interface LogbookEntry {
  when: number;
  name?: string;
  message?: string;
  entity_id?: string;
  state?: string;
  domain?: string;
  source?: string;
  context_user_id?: string;
  context_event_type?: string;
  context_name?: string;
  context_message?: string;
  context_entity_id?: string;
  context_domain?: string;
  context_service?: string;
}

export type Category = "warmwasser" | "wallbox" | "batterie" | "heizung" | "automation" | "sonstiges";

export const CATEGORY_LABEL: Record<Category, string> = {
  warmwasser: "Warmwasser",
  wallbox: "Wallbox",
  batterie: "Batterie",
  heizung: "Heizung",
  automation: "Automationen",
  sonstiges: "Sonstiges",
};

const RE: [Category, RegExp][] = [
  ["warmwasser", /ac ?thor|acthor|my ?pv|elwa|warmwasser|heizstab|tubratherm|boiler/],
  ["wallbox", /wallbox|charger|ocpp|go ?e|goe|epro|free2move|ladestation|lademodus|auto (sofort )?laden/],
  ["batterie", /batter|encharge|akku|powerwall|hausspeicher/],
  ["heizung", /^climate |climate |heizung|thermostat|fenster|froeling|pellet|kessel|sommerbetrieb|heizzeit|abwesen/],
];

// Einträge, die im Verlauf nur stören
const NOISE = /^(sun|weather|update|person|zone|device_tracker|event|tts|conversation|backup|sensor\.backup|binary_sensor\.remote_ui|image|camera|media_player)\b/;

export function categorize(e: LogbookEntry, extra: Record<string, Category> = {}): Category {
  if (e.entity_id && extra[e.entity_id]) return extra[e.entity_id];
  const text = norm(`${e.entity_id ?? ""} ${e.name ?? ""} ${e.message ?? ""} ${e.context_name ?? ""} ${e.context_entity_id ?? ""}`);
  for (const [cat, re] of RE) if (re.test(text)) return cat;
  const domain = e.domain ?? e.entity_id?.split(".")[0];
  if (domain === "automation" || domain === "script") return "automation";
  return "sonstiges";
}

export interface EventRow {
  key: string;
  first: number;
  last: number;
  count: number;
  category: Category;
  title: string;
  text: string;
  cause?: string;
  manual: boolean;
  decision: boolean;
}

/** Wer oder was hat es ausgelöst? */
export function describeCause(e: LogbookEntry, userNames: Record<string, string>): { cause?: string; manual: boolean } {
  if (e.context_event_type === "automation_triggered" && e.context_name) return { cause: `durch Automation „${e.context_name}“`, manual: false };
  if (e.context_event_type === "script_started" && e.context_name) return { cause: `durch Skript „${e.context_name}“`, manual: false };
  if (e.context_user_id) return { cause: `von Hand${userNames[e.context_user_id] ? ` (${userNames[e.context_user_id]})` : ""}`, manual: true };
  return { manual: false };
}

/** Logbuch-Texte von Home Assistant sind englisch – die häufigen übersetzen */
const PHRASES: [RegExp, string][] = [
  [/^triggered by /, "ausgelöst durch "],
  [/\bnumeric state of /, "Wert von "],
  [/\bstate of /, "Zustand von "],
  [/\btime pattern\b/, "Zeitraster"],
  [/\bHome Assistant starting\b/, "Start von Home Assistant"],
  [/\bHome Assistant stopping\b/, "Stopp von Home Assistant"],
  [/\bevent /, "Ereignis "],
  [/\bservice /, "Dienst "],
  [/\baction /, "Aktion "],
  [/\btemplate\b/, "Vorlage"],
  [/\bsun\b/, "Sonnenstand"],
  [/\btime\b/, "Uhrzeit"],
  [/^started$/, "gestartet"],
  [/^turned on$/, "eingeschaltet"],
  [/^turned off$/, "ausgeschaltet"],
];

export function translate(text: string): string {
  return PHRASES.reduce((t, [re, de]) => t.replace(re, de), text);
}

/** Gleiche Einträge mit höchstens diesem Abstand werden zu einer Zeile zusammengefasst */
const MERGE_GAP_MS = 20 * 60_000;

/**
 * Logbuch → Zeilen, neueste zuerst. Wiederkehrende gleiche Einträge (z. B. eine Automation, die
 * jede Minute läuft) werden zu einer Zeile mit Anzahl und Zeitspanne zusammengefasst.
 */
export function toRows(
  entries: LogbookEntry[],
  names: (id: string) => string,
  userNames: Record<string, string>,
  extra: Record<string, Category> = {},
  formatState: (id: string, state: string) => string = (_id, st) => stateText(st),
): EventRow[] {
  const rows: EventRow[] = [];
  const open = new Map<string, EventRow>();
  const sorted = [...entries].sort((a, b) => a.when - b.when);
  for (const e of sorted) {
    if (e.entity_id && NOISE.test(e.entity_id)) continue;
    // Skripte melden "started" und zusätzlich an/aus – das an/aus ist doppelt
    if (e.entity_id?.startsWith("script.") && e.state !== undefined && !e.message) continue;
    // Automationen: der Zustand an/aus ist aktivieren/deaktivieren, das Auslösen steht in message
    const category = categorize(e, extra);
    const decision = /^jotunland/i.test(e.name ?? "") && !!e.message && !e.entity_id?.startsWith("automation.") && !e.entity_id?.startsWith("script.");
    const title = e.name ?? (e.entity_id ? names(e.entity_id) : "Ereignis");
    // entity_ids in Meldungen ("Zustand von input_select.x") durch Namen ersetzen
    const message = e.message ? translate(e.message).replace(/\b[a-z_]+\.[a-z0-9_]+\b/g, (id) => names(id)) : undefined;
    const text = message ?? (e.state !== undefined ? `→ ${e.entity_id ? formatState(e.entity_id, e.state) : stateText(e.state)}` : "");
    const { cause, manual } = describeCause(e, userNames);
    const key = `${category}|${title}|${text}|${cause ?? ""}`;
    const t = e.when * 1000;
    const prev = open.get(key);
    if (prev && t - prev.last <= MERGE_GAP_MS) {
      prev.count++;
      prev.last = t;
      continue;
    }
    const row: EventRow = { key, first: t, last: t, count: 1, category, title, text, cause, manual, decision };
    open.set(key, row);
    rows.push(row);
  }
  return rows.sort((a, b) => b.last - a.last);
}

const STATE_DE: Record<string, string> = { on: "an", off: "aus", open: "offen", closed: "zu", heat: "Heizen", auto: "Automatik", unavailable: "nicht erreichbar", unknown: "unbekannt" };

export function stateText(s: string): string {
  return STATE_DE[s] ?? s;
}

export function useLogbook(from: number) {
  const { ws, status } = useHass();
  const [entries, setEntries] = useState<LogbookEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    if (status !== "connected") return;
    setLoading(true);
    setError(undefined);
    try {
      setEntries(await ws<LogbookEntry[]>({ type: "logbook/get_events", start_time: new Date(from).toISOString(), end_time: new Date().toISOString() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Logbuch nicht lesbar");
    } finally {
      setLoading(false);
    }
  }, [from, status, ws]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return { entries, loading, error, reload: load };
}
