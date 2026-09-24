import packageYaml from "../../homeassistant/packages/jotunland.yaml?raw";
import type { Mapping } from "./config";

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

/** Füllt das Paket mit den erkannten entity_ids. Fehlende bleiben als Platzhalter stehen. */
export function renderPackage(mapping: Mapping): { yaml: string; missing: string[] } {
  let yaml = packageYaml;
  const missing: string[] = [];
  for (const [placeholder, slot] of Object.entries(PLACEHOLDERS)) {
    const id = mapping[slot];
    if (id) yaml = yaml.split(placeholder).join(id);
    else missing.push(slot);
  }
  return { yaml, missing };
}
