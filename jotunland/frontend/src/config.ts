import { candidatesFor, SLOTS, type EntityInfo } from "./discovery";

export interface RoomConfig {
  name: string;
  climate: string;
  window?: string;
  humidity?: string;
}

type Group = Record<string, string | null | undefined>;

export interface JotunConfig {
  title: string;
  energy: Group;
  wallbox: Group;
  acthor: Group;
  pellet: Group;
  rooms: RoomConfig[];
}

export type Mapping = Record<string, string | undefined>;
export type MappingSource = "manual" | "config" | "auto" | "none";

export const EMPTY_CONFIG: JotunConfig = { title: "Jotunland", energy: {}, wallbox: {}, acthor: {}, pellet: {}, rooms: [] };

export async function loadConfig(): Promise<JotunConfig> {
  try {
    const res = await fetch(`./config.json?ts=${Date.now()}`);
    if (!res.ok) return EMPTY_CONFIG;
    return { ...EMPTY_CONFIG, ...(await res.json()) };
  } catch {
    return EMPTY_CONFIG;
  }
}

/**
 * Reihenfolge: in der App gewählt (manual) → config.json → automatisch erkannt.
 * Eine automatisch erkannte Entität wird nur einmal vergeben.
 */
export function resolveMapping(cfg: JotunConfig, overrides: Mapping, infos: EntityInfo[]): { mapping: Mapping; source: Record<string, MappingSource> } {
  const mapping: Mapping = {};
  const source: Record<string, MappingSource> = {};
  const used = new Set<string>();
  const pending: string[] = [];

  for (const key of Object.keys(SLOTS)) {
    const [group, name] = key.split(".") as [keyof JotunConfig, string];
    const manual = overrides[key];
    const explicit = (cfg[group] as Group | undefined)?.[name];
    if (manual) {
      mapping[key] = manual;
      source[key] = "manual";
    } else if (explicit) {
      mapping[key] = explicit;
      source[key] = "config";
    } else {
      pending.push(key);
      continue;
    }
    used.add(mapping[key]!);
  }
  for (const key of pending) {
    const best = candidatesFor(key, infos).find((c) => !used.has(c.id));
    mapping[key] = best?.id;
    source[key] = best ? "auto" : "none";
    if (best) used.add(best.id);
  }
  return { mapping, source };
}

/** Räume: aus config.json oder automatisch aus allen Thermostaten samt Fensterkontakt im selben Raum. */
export function resolveRooms(cfg: JotunConfig, infos: EntityInfo[], areaName: (id?: string) => string | undefined): RoomConfig[] {
  if (cfg.rooms?.length) return cfg.rooms;
  const areaOf = (i: EntityInfo) => i.meta?.area_id;
  return infos
    .filter((i) => i.domain === "climate")
    .map((c) => {
      const area = areaOf(c);
      const same = infos.filter((i) => area && areaOf(i) === area);
      return {
        name: areaName(area) ?? c.name,
        climate: c.id,
        window: same.find((i) => i.domain === "binary_sensor" && ["window", "door", "opening"].includes(i.deviceClass))?.id,
        humidity: same.find((i) => i.domain === "sensor" && i.deviceClass === "humidity")?.id,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name, "de"));
}
