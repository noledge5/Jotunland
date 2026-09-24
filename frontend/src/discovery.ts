import type { HassEntities, HassEntity } from "home-assistant-js-websocket";
import type { Area, DeviceInfo, EntityMeta } from "./ha/types";

/* ------------------------------------------------------------------------- *
 * Erkennung: findet zu jeder Funktion (PV-Leistung, Wallbox-Strom, …) die
 * passenden Entitäten und schlägt für Geräte verständliche Namen und Räume vor.
 * ------------------------------------------------------------------------- */

/** Kleinbuchstaben, Umlaute ausgeschrieben, Trennzeichen vereinheitlicht. */
export function norm(s: string): string {
  return s
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export interface EntityInfo {
  id: string;
  domain: string;
  entity: HassEntity;
  name: string;
  unit: string;
  deviceClass: string;
  device?: DeviceInfo;
  meta?: EntityMeta;
  /** normalisierter Suchtext: ID, Name, Gerät, Hersteller, Modell, Integration */
  text: string;
  /** normalisierter Hersteller-/Integrationstext */
  vendor: string;
}

export function buildInfos(entities: HassEntities, meta: Record<string, EntityMeta>, devices: Record<string, DeviceInfo>): EntityInfo[] {
  return Object.values(entities).map((entity) => {
    const m = meta[entity.entity_id];
    const device = m?.device_id ? devices[m.device_id] : undefined;
    const name = String(entity.attributes.friendly_name ?? entity.entity_id);
    const vendor = norm([m?.platform, device?.manufacturer, device?.model, device?.name].filter(Boolean).join(" "));
    return {
      id: entity.entity_id,
      domain: entity.entity_id.split(".")[0],
      entity,
      name,
      unit: String(entity.attributes.unit_of_measurement ?? ""),
      deviceClass: String(entity.attributes.device_class ?? ""),
      device,
      meta: m,
      text: norm(`${entity.entity_id} ${name} ${device?.name_by_user ?? ""} ${vendor}`),
      vendor,
    };
  });
}

/* ------------------------------- Zuordnung ------------------------------- */

export interface SlotRule {
  label: string;
  group: string;
  domains: string[];
  units?: string[];
  deviceClass?: string[];
  /** Hersteller/Integration, z. B. /enphase|envoy/ */
  vendor?: RegExp;
  /** Ohne Herstellertreffer wird die Entität nicht vorgeschlagen */
  vendorRequired?: boolean;
  /** Alle müssen im Suchtext vorkommen */
  need?: RegExp[];
  /** Jeder Treffer gibt Zusatzpunkte */
  bonus?: RegExp[];
  exclude?: RegExp;
  /** Zustand muss numerisch (true) bzw. Text (false) sein */
  numeric?: boolean;
}

const POWER = ["W", "kW"];
const ENERGY = ["kWh", "Wh", "MWh"];
const TEMP = ["°C"];

const ENPHASE = /enphase|envoy|iq gateway/;
const WALLBOX = /go ?e|goe|freecharge|free charge|wallbox|charger|ladestation|lader/;
const MYPV = /my ?pv|ac ?thor|acthor|elwa/;
const FROELING = /froeling|froling|lambdatronic|pellet|p4|pe1|s3 turbo/;

export const SLOTS: Record<string, SlotRule> = {
  "energy.pv_power": { group: "Solar (Enphase)", label: "PV-Leistung aktuell", domains: ["sensor"], units: POWER, vendor: ENPHASE, need: [/produc|produkt|erzeug|solar|pv/], exclude: /consum|verbrauch|inverter|wechselrichter|\bnet\b|today|heute|lifetime|gesamt|7 ?day/ },
  "energy.pv_today": { group: "Solar (Enphase)", label: "PV-Ertrag heute", domains: ["sensor"], units: ENERGY, vendor: ENPHASE, need: [/produc|produkt|erzeug|solar|pv/, /today|heute|tag/], exclude: /consum|verbrauch|inverter/ },
  "energy.consumption": { group: "Solar (Enphase)", label: "Hausverbrauch aktuell", domains: ["sensor"], units: POWER, vendor: ENPHASE, need: [/consum|verbrauch/], exclude: /\bnet\b|netto|today|heute|lifetime|7 ?day/ },
  "energy.grid": { group: "Solar (Enphase)", label: "Netz (+Bezug / −Einspeisung)", domains: ["sensor"], units: POWER, vendor: /enphase|envoy|smart meter|zaehler|shelly em|tibber/, need: [/\bnet\b|grid|bezug|zaehler/], exclude: /today|heute|lifetime/ },

  "wallbox.status": { group: "Wallbox", label: "Status", domains: ["sensor"], vendor: WALLBOX, vendorRequired: true, need: [/status|state|zustand|car/], numeric: false, exclude: /error|fehler/ },
  "wallbox.power": { group: "Wallbox", label: "Ladeleistung", domains: ["sensor"], units: POWER, vendor: WALLBOX, vendorRequired: true, bonus: [/power|leistung|nrg|charging|laden/], exclude: /\b(max|limit|l[123]|phase)\b/ },
  "wallbox.session_energy": { group: "Wallbox", label: "Geladen (Sitzung)", domains: ["sensor"], units: ENERGY, vendor: WALLBOX, vendorRequired: true, bonus: [/session|geladen|charged|\bwh\b/], exclude: /total|gesamt|eto/ },
  "wallbox.charging_switch": { group: "Wallbox", label: "Laden an/aus", domains: ["switch", "select"], vendor: WALLBOX, vendorRequired: true, bonus: [/charg|laden|frc|force|allow|start/] },
  "wallbox.current": { group: "Wallbox", label: "Ladestrom", domains: ["number", "input_number"], units: ["A"], vendor: WALLBOX, vendorRequired: true, bonus: [/amp|strom|current/], exclude: /\b(max|min|limit)\b/ },
  "wallbox.mode": { group: "Wallbox", label: "Lademodus (Jotunland)", domains: ["input_select"], need: [/jotunland/, /wallbox|lade/] },

  "acthor.power": { group: "AC THOR / Warmwasser", label: "Heizleistung", domains: ["sensor"], units: POWER, vendor: MYPV, vendorRequired: true, bonus: [/power|leistung/] },
  "acthor.temperature": { group: "AC THOR / Warmwasser", label: "Warmwasser-Temperatur", domains: ["sensor"], units: TEMP, vendor: MYPV, vendorRequired: true, bonus: [/temp|wasser|boiler|speicher/], exclude: /soll|target|\b(max|min)\b/ },
  "acthor.target": { group: "AC THOR / Warmwasser", label: "Warmwasser-Soll", domains: ["number", "input_number"], units: TEMP, vendor: MYPV, vendorRequired: true, bonus: [/soll|target|\bww\b|max/] },

  "pellet.state": { group: "Pelletkessel (Fröling)", label: "Kesselzustand", domains: ["sensor"], vendor: FROELING, vendorRequired: true, need: [/zustand|state|status|betrieb/], numeric: false, exclude: /stoer|error|fehler/ },
  "pellet.boiler_temp": { group: "Pelletkessel (Fröling)", label: "Kesseltemperatur", domains: ["sensor"], units: TEMP, vendor: FROELING, vendorRequired: true, need: [/kessel|boiler/], exclude: /soll|target|abgas|rueck/ },
  "pellet.buffer_top": { group: "Pelletkessel (Fröling)", label: "Puffer oben", domains: ["sensor"], units: TEMP, need: [/puffer|buffer/, /oben|top|fuehler 1/], vendor: FROELING },
  "pellet.buffer_bottom": { group: "Pelletkessel (Fröling)", label: "Puffer unten", domains: ["sensor"], units: TEMP, need: [/puffer|buffer/, /unten|bottom|fuehler 2/], vendor: FROELING },
  "pellet.outside_temp": { group: "Pelletkessel (Fröling)", label: "Außentemperatur", domains: ["sensor"], units: TEMP, need: [/aussen|outside|outdoor|draussen/], vendor: FROELING },
  "pellet.pellet_stock": { group: "Pelletkessel (Fröling)", label: "Pelletvorrat", domains: ["sensor"], units: ["%", "kg", "t"], vendor: FROELING, vendorRequired: true, need: [/vorrat|lager|stock|fuel|fuell|pellet/] },
  "pellet.error": { group: "Pelletkessel (Fröling)", label: "Störung", domains: ["binary_sensor", "sensor"], vendor: FROELING, vendorRequired: true, need: [/stoer|error|fehler|problem/] },
};

export interface Candidate {
  id: string;
  score: number;
  reasons: string[];
}

export function scoreEntity(rule: SlotRule, e: EntityInfo): Candidate | null {
  if (!rule.domains.includes(e.domain)) return null;
  if (rule.exclude?.test(e.text)) return null;
  const numeric = e.entity.state !== "" && !isNaN(Number(e.entity.state));
  if (rule.numeric === false && numeric) return null;
  if (rule.units?.length && !rule.units.includes(e.unit)) return null;

  let score = 1;
  const reasons: string[] = [];
  const vendorHit = !!rule.vendor && (rule.vendor.test(e.vendor) || rule.vendor.test(e.text));
  if (rule.vendorRequired && !vendorHit) return null;
  if (vendorHit) {
    score += 4;
    reasons.push(e.device?.manufacturer ?? e.meta?.platform ?? "Hersteller");
  }
  for (const re of rule.need ?? []) {
    if (!re.test(e.text)) return null;
    score += 3;
  }
  if (rule.need?.length) reasons.push("Name passt");
  for (const re of rule.bonus ?? []) {
    if (re.test(e.text)) {
      score += 2;
      reasons.push("Stichwort");
    }
  }
  if (rule.units?.length) {
    score += 2;
    reasons.push(`Einheit ${e.unit}`);
  }
  if (rule.deviceClass?.includes(e.deviceClass)) score += 1;
  if (e.entity.state === "unavailable") score -= 2;
  return { id: e.id, score, reasons };
}

export function candidatesFor(slot: string, infos: EntityInfo[]): Candidate[] {
  const rule = SLOTS[slot];
  return infos
    .map((i) => scoreEntity(rule, i))
    .filter((c): c is Candidate => !!c)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}

/* ----------------------------- Geräte-Typen ----------------------------- */

export type Kind =
  | "thermostat" | "window" | "door" | "light" | "plug" | "switch" | "motion" | "climate_sensor" | "remote"
  | "cover" | "pv" | "wallbox" | "acthor" | "pellet" | "water_leak" | "smoke" | "other";

export const KIND_LABEL: Record<Kind, string> = {
  thermostat: "Heizkörperthermostat",
  window: "Fensterkontakt",
  door: "Türkontakt",
  light: "Licht",
  plug: "Steckdose",
  switch: "Schalter",
  motion: "Bewegungsmelder",
  climate_sensor: "Klimasensor",
  remote: "Taster",
  cover: "Rollladen",
  pv: "PV-Anlage",
  wallbox: "Wallbox",
  acthor: "AC THOR",
  pellet: "Pelletkessel",
  water_leak: "Wassermelder",
  smoke: "Rauchmelder",
  other: "Gerät",
};

/** Kurzform für Namensvorschläge ("Thermostat Wohnzimmer") */
const KIND_SHORT: Partial<Record<Kind, string>> = { thermostat: "Thermostat", climate_sensor: "Klima", window: "Fenster", door: "Tür" };

export function classify(infos: EntityInfo[], vendorText: string): Kind {
  const v = vendorText;
  if (ENPHASE.test(v)) return "pv";
  if (MYPV.test(v)) return "acthor";
  if (FROELING.test(v)) return "pellet";
  if (WALLBOX.test(v)) return "wallbox";
  const has = (domain: string, dc?: string[]) => infos.some((i) => i.domain === domain && (!dc || dc.includes(i.deviceClass)));
  if (has("climate")) return "thermostat";
  if (has("cover")) return "cover";
  if (has("light")) return "light";
  if (has("binary_sensor", ["window"])) return "window";
  if (has("binary_sensor", ["door", "garage_door", "opening"])) return /tuer|door/.test(v) ? "door" : "window";
  if (has("binary_sensor", ["motion", "occupancy", "presence"])) return "motion";
  if (has("binary_sensor", ["moisture"])) return "water_leak";
  if (has("binary_sensor", ["smoke"])) return "smoke";
  if (has("switch") && has("sensor", ["power", "energy"])) return "plug";
  if (has("switch")) return "switch";
  if (has("event") || infos.some((i) => /action|click/.test(i.id))) return "remote";
  if (has("sensor", ["temperature"]) || has("sensor", ["humidity"])) return "climate_sensor";
  return "other";
}

/** Namen, die nach Firmware/Adresse statt nach Mensch aussehen. */
export function looksTechnical(name: string, device?: DeviceInfo): boolean {
  const n = name.trim();
  if (!n) return true;
  if (/0x[0-9a-f]{6,}/i.test(n)) return true; // Zigbee-IEEE-Adresse
  if (/^[A-Z]{1,4}[_-]?\d{3,}/.test(n)) return true; // TS0601, SNZB-02 …
  if (/lumi\.|_TZ|_tz\d|tuya|xiaomi|aqara|sonoff|ikea of/i.test(n)) return true;
  if (/_/.test(n) && !/\s/.test(n)) return true;
  if (device?.model && norm(n) === norm(device.model)) return true;
  if (device?.manufacturer && norm(n).startsWith(norm(device.manufacturer))) return true;
  return false;
}

/** Raum anhand von Namen/ID raten, z. B. "trv_wohnzimmer" → Wohnzimmer */
export function guessArea(text: string, areas: Area[]): Area | undefined {
  const t = ` ${norm(text)} `;
  const hits = areas.filter((a) => {
    const an = norm(a.name);
    return an.length > 2 && (t.includes(` ${an} `) || t.includes(an.replace(/ /g, "")));
  });
  // längster Treffer gewinnt ("Kinderzimmer" vor "Zimmer")
  return hits.sort((a, b) => b.name.length - a.name.length)[0];
}

export interface DeviceSuggestion {
  device: DeviceInfo;
  kind: Kind;
  entities: EntityInfo[];
  currentName: string;
  technical: boolean;
  areaName?: string;
  suggestedName?: string;
  suggestedArea?: Area;
}

export function suggestDevices(infos: EntityInfo[], devices: Record<string, DeviceInfo>, areas: Area[]): DeviceSuggestion[] {
  const byDevice = new Map<string, EntityInfo[]>();
  for (const i of infos) {
    const d = i.meta?.device_id;
    if (!d) continue;
    byDevice.set(d, [...(byDevice.get(d) ?? []), i]);
  }
  const areaById = new Map(areas.map((a) => [a.area_id, a]));
  const out: DeviceSuggestion[] = [];
  for (const [id, ents] of byDevice) {
    const device = devices[id];
    if (!device) continue;
    const currentName = device.name_by_user || device.name || id;
    const vendorText = norm(`${device.manufacturer ?? ""} ${device.model ?? ""} ${ents[0]?.meta?.platform ?? ""} ${currentName}`);
    const kind = classify(ents, vendorText);
    const area = device.area_id ? areaById.get(device.area_id) : undefined;
    const suggestedArea = area ? undefined : guessArea(`${currentName} ${ents.map((e) => `${e.id} ${e.name}`).join(" ")}`, areas);
    const technical = looksTechnical(currentName, device);
    out.push({ device, kind, entities: ents, currentName, technical, areaName: area?.name, suggestedArea });
  }

  // Namensvorschläge: "<Typ> <Raum>", bei Dopplungen durchnummeriert
  const seen = new Map<string, number>();
  const total = new Map<string, number>();
  const baseName = (s: DeviceSuggestion) => {
    const room = s.areaName ?? s.suggestedArea?.name;
    const label = KIND_SHORT[s.kind] ?? KIND_LABEL[s.kind];
    if (["pv", "wallbox", "acthor", "pellet"].includes(s.kind)) return KIND_LABEL[s.kind];
    return room ? `${label} ${room}` : undefined;
  };
  for (const s of out) {
    const b = baseName(s);
    if (b) total.set(b, (total.get(b) ?? 0) + 1);
  }
  for (const s of out) {
    const b = baseName(s);
    if (!b || s.kind === "other" || !s.technical) continue;
    const n = (seen.get(b) ?? 0) + 1;
    seen.set(b, n);
    const name = (total.get(b) ?? 1) > 1 ? `${b} ${n}` : b;
    if (norm(name) !== norm(s.currentName)) s.suggestedName = name;
  }
  return out.sort((a, b) => Number(b.technical) - Number(a.technical) || a.currentName.localeCompare(b.currentName, "de"));
}
