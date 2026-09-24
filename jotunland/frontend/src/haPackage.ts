import packageYaml from "../../homeassistant/packages/jotunland.yaml?raw";
import type { Mapping, RoomConfig } from "./config";
import { norm } from "./discovery";

/** Version des mitgelieferten Pakets – das Add-on meldet die installierte. */
export const PACKAGE_VERSION = Number(/jotunland-package-version:\s*(\d+)/.exec(packageYaml)?.[1] ?? 0);

/** Platzhalter im HA-Paket → Zuordnungsschlüssel im Frontend */
export const PLACEHOLDERS: Record<string, string> = {
  "sensor.anpassen_pv_leistung": "energy.pv_power",
  "sensor.anpassen_hausverbrauch": "energy.consumption",
  "sensor.anpassen_wallbox_leistung": "wallbox.power",
  "sensor.anpassen_wallbox_geladen": "wallbox.session_energy",
  "switch.anpassen_wallbox_laden": "wallbox.charging_switch",
  "number.anpassen_wallbox_ladestrom": "wallbox.current",
  "sensor.anpassen_warmwasser_temperatur": "acthor.temperature",
  "binary_sensor.anpassen_kessel_stoerung": "pellet.error",
  "sensor.anpassen_pelletvorrat": "pellet.pellet_stock",
};

/** Pro Fensterkontakt eine Automation aus dem Blueprint – alle Thermostate im selben Raum. */
function windowAutomations(rooms: RoomConfig[]): string {
  const byWindow = new Map<string, { names: string[]; climates: string[] }>();
  for (const r of rooms) {
    if (!r.window) continue;
    const g = byWindow.get(r.window) ?? { names: [], climates: [] };
    if (!g.names.includes(r.name)) g.names.push(r.name);
    g.climates.push(r.climate);
    byWindow.set(r.window, g);
  }
  if (!byWindow.size) return "";
  const q = (s: string) => JSON.stringify(s);
  const blocks = [...byWindow.entries()].map(([win, g]) => {
    const slug = norm(g.names[0]).replace(/ /g, "_") || win.split(".")[1];
    return [
      `  - id: jotunland_fenster_${slug}`,
      `    alias: ${q(`Fenster offen → Heizung aus (${g.names.join(", ")})`)}`,
      `    use_blueprint:`,
      `      path: jotunland/fenster_offen_heizung_aus.yaml`,
      `      input:`,
      `        fenster:`,
      `          - ${win}`,
      `        thermostat:`,
      ...g.climates.map((c) => `          - ${c}`),
      `        verzoegerung: 30`,
    ].join("\n");
  });
  return `\n  # ------------------------------------------ Fenster (automatisch erzeugt)\n${blocks.join("\n\n")}\n`;
}

/** Füllt das Paket mit den erkannten entity_ids. Fehlende bleiben als Platzhalter stehen. */
export function renderPackage(mapping: Mapping, rooms: RoomConfig[] = []): { yaml: string; missing: string[] } {
  let yaml = packageYaml;
  const missing: string[] = [];
  for (const [placeholder, slot] of Object.entries(PLACEHOLDERS)) {
    const id = mapping[slot];
    if (id) yaml = yaml.split(placeholder).join(id);
    else missing.push(slot);
  }
  // "automation:" ist der letzte Abschnitt des Pakets → Fenster-Automationen anhängen
  yaml = yaml.trimEnd() + "\n" + windowAutomations(rooms);
  return { yaml, missing };
}

/** Startwerte für die Helfer (gleiche Werte wie im Add-on-Server). */
export const HELPER_DEFAULTS: Record<string, number | string> = {
  "input_number.jotunland_wallbox_max_ampere": 16,
  "input_number.jotunland_wallbox_phasen": 3,
  "input_number.jotunland_komfort_temperatur": 21,
  "input_number.jotunland_eco_temperatur": 18,
  "input_number.jotunland_warmwasser_minimum": 45,
  "input_datetime.jotunland_heizen_start": "06:00:00",
  "input_datetime.jotunland_heizen_ende": "22:00:00",
};
