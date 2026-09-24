import { useMemo } from "react";
import { useHass } from "./ha/HassContext";
import { suggestDevices, type DeviceSuggestion } from "./discovery";
import { HELPER_DEFAULTS, PACKAGE_VERSION, renderPackage } from "./haPackage";

/** Die wichtigsten Funktionen je Gerät – daran misst der Assistent "erkannt". */
export const CORE_SLOTS: { group: string; slots: string[] }[] = [
  { group: "Solar", slots: ["energy.pv_power"] },
  { group: "Wallbox", slots: ["wallbox.power", "wallbox.charging_switch"] },
  { group: "AC THOR", slots: ["acthor.temperature", "acthor.power"] },
  { group: "Pelletkessel", slots: ["pellet.boiler_temp", "pellet.state"] },
];

export const HELPER_MARKER = "input_select.jotunland_wallbox_modus";

/** Adapter- und Hilfsskripte des Pakets – Bausteine der Automationen, keine Schnellaktionen */
export const INTERNAL_SCRIPT = /^script\.jotunland_(wallbox_(start|stop|strom)|pellet_anfordern|melden|thermostate)$/;

/** Was ist eingerichtet, was fehlt noch? Grundlage für Assistent und Hinweis auf der Übersicht. */
export function useSetupState() {
  const { infos, devices, areas, entities, mapping, rooms, addon, registryAvailable } = useHass();

  return useMemo(() => {
    const suggestions = registryAvailable ? suggestDevices(infos, devices, areas).filter((s) => s.suggestedName || s.suggestedArea) : [];
    const groups = CORE_SLOTS.map((g) => ({ group: g.group, found: g.slots.some((s) => !!mapping[s]) }));
    const pkg = renderPackage(mapping, rooms);
    const helpersInstalled = !!entities[HELPER_MARKER];
    const packageCurrent = addon ? addon.package.installed && (addon.package.version ?? 0) >= PACKAGE_VERSION : helpersInstalled;
    const helpersNeedingDefaults = Object.keys(HELPER_DEFAULTS).filter((id) => needsDefault(entities[id]));
    const windowRooms = rooms.filter((r) => r.window).length;
    const open = [!packageCurrent, suggestions.length > 0, helpersInstalled && helpersNeedingDefaults.length > 0].filter(Boolean).length;
    return { suggestions, groups, pkg, helpersInstalled, packageCurrent, helpersNeedingDefaults, windowRooms, open };
  }, [infos, devices, areas, entities, mapping, rooms, addon, registryAvailable]);
}

function needsDefault(e?: { state: string; attributes: Record<string, unknown> }): boolean {
  if (!e) return false;
  if (e.attributes.has_time !== undefined) return e.state === "00:00:00";
  return e.attributes.min !== undefined && Number(e.state) === Number(e.attributes.min);
}

export function useSetupActions() {
  const { ws, refreshRegistry, callService, entities, addonApi, refreshAddon } = useHass();

  const applySuggestions = async (list: DeviceSuggestion[]) => {
    for (const s of list) {
      const msg: Record<string, unknown> = { type: "config/device_registry/update", device_id: s.device.id };
      if (s.suggestedName) msg.name_by_user = s.suggestedName;
      if (s.suggestedArea) msg.area_id = s.suggestedArea.area_id;
      await ws(msg);
    }
    await refreshRegistry();
  };

  const applyDefaults = async () => {
    for (const [id, value] of Object.entries(HELPER_DEFAULTS)) {
      if (!needsDefault(entities[id])) continue;
      if (id.startsWith("input_datetime.")) await callService("input_datetime", "set_datetime", { entity_id: id, time: value });
      else await callService("input_number", "set_value", { entity_id: id, value });
    }
  };

  const installPackage = async (yaml: string) => {
    const res = await addonApi<{ ok: boolean; steps: string[]; restarting: boolean }>("install", { yaml, restart: true });
    await refreshAddon();
    return res;
  };

  return { applySuggestions, applyDefaults, installPackage };
}
