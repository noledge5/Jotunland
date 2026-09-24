import type { HassEntity } from "home-assistant-js-websocket";

const nf = (digits: number) => new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const isNumeric = (e?: HassEntity) => !!e && e.state !== "" && !isNaN(Number(e.state));
export const unavailable = (e?: HassEntity) => !e || e.state === "unavailable" || e.state === "unknown";

export function num(e?: HassEntity): number | undefined {
  return isNumeric(e) ? Number(e!.state) : undefined;
}

/** Leistung in Watt, unabhängig davon ob der Sensor W, kW oder MW meldet. */
export function watts(e?: HassEntity): number | undefined {
  const v = num(e);
  if (v === undefined) return undefined;
  const u = String(e!.attributes.unit_of_measurement ?? "W");
  return u === "kW" ? v * 1000 : u === "MW" ? v * 1e6 : v;
}

export function fmtPower(w?: number): string {
  if (w === undefined) return "–";
  const a = Math.abs(w);
  return a >= 1000 ? `${nf(1).format(w / 1000)} kW` : `${nf(0).format(w)} W`;
}

export function fmtNum(v: number | undefined, digits = 1): string {
  return v === undefined ? "–" : nf(digits).format(v);
}

export function fmtTemp(v: number | undefined): string {
  return v === undefined ? "–" : `${nf(1).format(v)} °C`;
}

export function name(e?: HassEntity, fallback = ""): string {
  return (e?.attributes.friendly_name as string | undefined) ?? e?.entity_id ?? fallback;
}

const STATE_DE: Record<string, string> = {
  on: "An", off: "Aus", open: "Offen", closed: "Geschlossen", opening: "Öffnet", closing: "Schließt",
  unavailable: "Nicht erreichbar", unknown: "Unbekannt", heat: "Heizen", auto: "Automatik", cool: "Kühlen",
  heating: "heizt", idle: "hält", home: "Zuhause", not_home: "Abwesend",
};

export function fmtState(e?: HassEntity): string {
  if (!e) return "–";
  if (isNumeric(e)) {
    const v = Number(e.state);
    const unit = e.attributes.unit_of_measurement ? ` ${e.attributes.unit_of_measurement}` : "";
    return `${nf(Number.isInteger(v) ? 0 : 1).format(v)}${unit}`;
  }
  if (e.entity_id.startsWith("binary_sensor.")) {
    const dc = e.attributes.device_class;
    if (dc === "window" || dc === "door" || dc === "opening") return e.state === "on" ? "Offen" : "Geschlossen";
    if (dc === "problem") return e.state === "on" ? "Störung" : "OK";
    if (dc === "motion" || dc === "occupancy") return e.state === "on" ? "Erkannt" : "Frei";
  }
  return STATE_DE[e.state] ?? e.state;
}

export function relTime(iso?: string | null): string {
  if (!iso) return "nie";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "gerade eben";
  if (diff < 3600) return `vor ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `vor ${Math.floor(diff / 3600)} h`;
  return new Date(iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export { norm } from "./discovery";

/** Solltemperatur eines Thermostats: Einzelwert oder Bereich (Heizen/Kühlen) */
export function fmtTarget(a: Record<string, unknown>): string {
  const n = (v: unknown) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? undefined : Number(v));
  const t = n(a.temperature);
  if (t !== undefined) return `${fmtNum(t, 1)}°`;
  const lo = n(a.target_temp_low);
  const hi = n(a.target_temp_high);
  return lo !== undefined && hi !== undefined ? `${fmtNum(lo, 0)}–${fmtNum(hi, 0)}°` : "–";
}
