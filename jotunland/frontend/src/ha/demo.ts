import type { HassEntities, HassEntity } from "home-assistant-js-websocket";
import type { Area, DeviceInfo, RegEntity } from "./types";

/**
 * Simuliertes Zuhause für den Demo-Modus (?demo in der URL oder im Einrichtungsdialog).
 * Die entity_ids ähneln denen der echten Integrationen, damit die automatische
 * Zuordnung sichtbar funktioniert.
 */

const now = () => new Date().toISOString();

function e(entity_id: string, state: string | number, attributes: Record<string, unknown> = {}): HassEntity {
  const t = now();
  return {
    entity_id,
    state: String(state),
    attributes: { friendly_name: entity_id, ...attributes },
    last_changed: t,
    last_updated: t,
    context: { id: "demo", user_id: null, parent_id: null },
  };
}

const thermostat = (id: string, name: string, cur: number, target: number) =>
  e(`climate.${id}`, "heat", {
    friendly_name: name,
    current_temperature: cur,
    temperature: target,
    min_temp: 5,
    max_temp: 30,
    target_temp_step: 0.5,
    hvac_modes: ["heat", "auto", "off"],
    hvac_action: cur < target ? "heating" : "idle",
    battery: 60 + Math.round(Math.random() * 40),
  });

export const demoAreas: Area[] = [
  { area_id: "wohnzimmer", name: "Wohnzimmer" },
  { area_id: "kueche", name: "Küche" },
  { area_id: "schlafzimmer", name: "Schlafzimmer" },
  { area_id: "bad", name: "Bad" },
  { area_id: "technik", name: "Technikraum" },
  { area_id: "garage", name: "Garage" },
];

// Bewusst teils "technische" Namen und fehlende Räume, wie frisch angelernte Zigbee-Geräte.
const DEVICES: (DeviceInfo & { platform: string; entities: string[] })[] = [
  { id: "d_envoy", name: "Envoy 122301", manufacturer: "Enphase", model: "Envoy-S Metered", area_id: "technik", platform: "enphase_envoy", entities: ["sensor.envoy_122301_current_power_production", "sensor.envoy_122301_energy_production_today", "sensor.envoy_122301_current_power_consumption", "sensor.envoy_122301_current_net_power_consumption"] },
  { id: "d_goe", name: "go-eCharger 204512", manufacturer: "go-e", model: "Gemini flex 11kW", area_id: null, platform: "goecharger_api2", entities: ["sensor.wallbox_status", "sensor.wallbox_leistung", "sensor.wallbox_geladen_session", "switch.wallbox_laden", "number.wallbox_ladestrom_ampere"] },
  { id: "d_thor", name: "AC THOR 9s", manufacturer: "my-PV", model: "AC•THOR 9s", area_id: "technik", platform: "mypv", entities: ["sensor.ac_thor_leistung", "sensor.ac_thor_temperatur", "number.ac_thor_soll_temperatur"] },
  { id: "d_froeling", name: "Fröling P4", manufacturer: "Fröling", model: "Lambdatronic P 3200", area_id: "technik", platform: "froeling_connect", entities: ["sensor.froeling_kesselzustand", "sensor.froeling_kesseltemperatur", "sensor.froeling_puffer_oben", "sensor.froeling_puffer_unten", "sensor.aussentemperatur", "sensor.froeling_pelletvorrat", "binary_sensor.froeling_stoerung"] },
  { id: "d_trv1", name: "0x00158d0004a1b2c3", manufacturer: "_TZE200_ckud7u2l", model: "TS0601", area_id: "wohnzimmer", platform: "zha", entities: ["climate.wohnzimmer"] },
  { id: "d_trv2", name: "Thermostat Küche", manufacturer: "Bosch", model: "BTH-RA", area_id: "kueche", platform: "zha", entities: ["climate.kueche"] },
  { id: "d_trv3", name: "TS0601_thermostat", manufacturer: "_TZE200_hue3yfsn", model: "TS0601", area_id: null, platform: "zha", entities: ["climate.schlafzimmer"] },
  { id: "d_trv4", name: "Thermostat Bad", manufacturer: "Danfoss", model: "eTRV0100", area_id: "bad", platform: "zha", entities: ["climate.bad"] },
  { id: "d_win1", name: "lumi.sensor_magnet.aq2", manufacturer: "LUMI", model: "lumi.sensor_magnet.aq2", area_id: "wohnzimmer", platform: "zha", entities: ["binary_sensor.fenster_wohnzimmer"] },
  { id: "d_win2", name: "0x00158d00045d6e7f", manufacturer: "LUMI", model: "lumi.sensor_magnet.aq2", area_id: null, platform: "zha", entities: ["binary_sensor.fenster_schlafzimmer"] },
  { id: "d_win3", name: "Fenster Bad", manufacturer: "Aqara", model: "MCCGQ11LM", area_id: "bad", platform: "zha", entities: ["binary_sensor.fenster_bad"] },
  { id: "d_hum", name: "SNZB-02", manufacturer: "SONOFF", model: "SNZB-02", area_id: "bad", platform: "zha", entities: ["sensor.bad_luftfeuchtigkeit"] },
  { id: "d_temp", name: "Temperatur Wohnzimmer", manufacturer: "Aqara", model: "WSDCGQ11LM", area_id: "wohnzimmer", platform: "zha", entities: ["sensor.wohnzimmer_temperatur"] },
  { id: "d_l1", name: "IKEA of Sweden TRADFRI bulb E27 WS", manufacturer: "IKEA of Sweden", model: "TRADFRI bulb E27 WS opal 980lm", area_id: "wohnzimmer", platform: "zha", entities: ["light.wohnzimmer_decke"] },
  { id: "d_l2", name: "Stehlampe", manufacturer: "Philips", model: "LCA001", area_id: "wohnzimmer", platform: "zha", entities: ["light.wohnzimmer_stehlampe"] },
  { id: "d_l3", name: "Küchenlicht", manufacturer: "IKEA of Sweden", model: "TRADFRI Driver 30W", area_id: "kueche", platform: "zha", entities: ["light.kueche"] },
  { id: "d_l4", name: "Nachttisch", manufacturer: "Innr", model: "RB 285 C", area_id: "schlafzimmer", platform: "zha", entities: ["light.schlafzimmer"] },
  { id: "d_plug", name: "S26R2ZB", manufacturer: "SONOFF", model: "S26R2ZB", area_id: "kueche", platform: "zha", entities: ["switch.kaffeemaschine", "sensor.kaffeemaschine_leistung"] },
  { id: "d_rollo", name: "Rollo Wohnzimmer", manufacturer: "Ubisys", model: "J1", area_id: "wohnzimmer", platform: "zha", entities: ["cover.wohnzimmer_rollo"] },
];

export interface DemoRegistry {
  devices: DeviceInfo[];
  entities: RegEntity[];
}

function initialRegistry(): DemoRegistry {
  return {
    devices: DEVICES.map(({ platform: _p, entities: _e, ...d }) => ({ ...d })),
    entities: DEVICES.flatMap((d) => d.entities.map((entity_id) => ({ entity_id, device_id: d.id, platform: d.platform, area_id: null }))),
  };
}

function initialStates(): HassEntities {
  const list: HassEntity[] = [
    e("sensor.envoy_122301_current_power_production", 5230, { friendly_name: "Envoy Aktuelle Produktion", unit_of_measurement: "W", device_class: "power" }),
    e("sensor.envoy_122301_energy_production_today", 21.4, { friendly_name: "Envoy Produktion heute", unit_of_measurement: "kWh", device_class: "energy" }),
    e("sensor.envoy_122301_current_power_consumption", 1480, { friendly_name: "Envoy Aktueller Verbrauch", unit_of_measurement: "W", device_class: "power" }),
    e("sensor.envoy_122301_current_net_power_consumption", -3750, { friendly_name: "Envoy Netz", unit_of_measurement: "W", device_class: "power" }),

    e("sensor.wallbox_status", "Lädt", { friendly_name: "Wallbox Status" }),
    e("sensor.wallbox_leistung", 0, { friendly_name: "Wallbox Leistung", unit_of_measurement: "W", device_class: "power" }),
    e("sensor.wallbox_geladen_session", 7.8, { friendly_name: "Wallbox geladen", unit_of_measurement: "kWh", device_class: "energy" }),
    e("switch.wallbox_laden", "on", { friendly_name: "Wallbox Laden" }),
    e("number.wallbox_ladestrom_ampere", 10, { friendly_name: "Wallbox Ladestrom", min: 6, max: 16, step: 1, unit_of_measurement: "A" }),

    e("sensor.ac_thor_leistung", 900, { friendly_name: "AC THOR Leistung", unit_of_measurement: "W", device_class: "power" }),
    e("sensor.ac_thor_temperatur", 54.5, { friendly_name: "Warmwasser", unit_of_measurement: "°C", device_class: "temperature" }),
    e("number.ac_thor_soll_temperatur", 60, { friendly_name: "Warmwasser Soll", min: 40, max: 75, step: 1, unit_of_measurement: "°C" }),

    e("sensor.froeling_kesselzustand", "Heizen", { friendly_name: "Kesselzustand" }),
    e("sensor.froeling_kesseltemperatur", 71, { friendly_name: "Kesseltemperatur", unit_of_measurement: "°C", device_class: "temperature" }),
    e("sensor.froeling_puffer_oben", 66, { friendly_name: "Puffer oben", unit_of_measurement: "°C", device_class: "temperature" }),
    e("sensor.froeling_puffer_unten", 41, { friendly_name: "Puffer unten", unit_of_measurement: "°C", device_class: "temperature" }),
    e("sensor.aussentemperatur", 8.5, { friendly_name: "Außentemperatur", unit_of_measurement: "°C", device_class: "temperature" }),
    e("sensor.froeling_pelletvorrat", 38, { friendly_name: "Pelletvorrat", unit_of_measurement: "%" }),
    e("binary_sensor.froeling_stoerung", "off", { friendly_name: "Kessel Störung", device_class: "problem" }),

    thermostat("wohnzimmer", "Wohnzimmer", 21.2, 21.5),
    thermostat("kueche", "Küche", 20.1, 20),
    thermostat("schlafzimmer", "Schlafzimmer", 18.4, 18),
    thermostat("bad", "Bad", 21.8, 23),

    e("light.wohnzimmer_decke", "on", { friendly_name: "Deckenlicht", brightness: 180, supported_color_modes: ["brightness"] }),
    e("light.wohnzimmer_stehlampe", "off", { friendly_name: "Stehlampe", supported_color_modes: ["brightness"] }),
    e("light.kueche", "off", { friendly_name: "Küchenlicht", supported_color_modes: ["onoff"] }),
    e("light.schlafzimmer", "off", { friendly_name: "Nachttisch", supported_color_modes: ["brightness"] }),
    e("switch.kaffeemaschine", "off", { friendly_name: "Kaffeemaschine" }),
    e("sensor.kaffeemaschine_leistung", 0, { friendly_name: "Kaffeemaschine Leistung", unit_of_measurement: "W", device_class: "power" }),
    e("cover.wohnzimmer_rollo", "open", { friendly_name: "Rollo", current_position: 100 }),
    e("binary_sensor.fenster_wohnzimmer", "off", { friendly_name: "Fenster Wohnzimmer", device_class: "window" }),
    e("binary_sensor.fenster_schlafzimmer", "on", { friendly_name: "Fenster Schlafzimmer", device_class: "window" }),
    e("binary_sensor.fenster_bad", "off", { friendly_name: "Fenster Bad", device_class: "window" }),
    e("sensor.bad_luftfeuchtigkeit", 64, { friendly_name: "Luftfeuchtigkeit Bad", unit_of_measurement: "%", device_class: "humidity" }),
    e("sensor.wohnzimmer_temperatur", 21.2, { friendly_name: "Temperatur Wohnzimmer", unit_of_measurement: "°C", device_class: "temperature" }),

    e("input_boolean.jotunland_abwesend", "off", { friendly_name: "Abwesend", icon: "mdi:airplane" }),
    e("input_boolean.jotunland_sommerbetrieb", "off", { friendly_name: "Sommerbetrieb (Pellets aus)" }),
    e("input_select.jotunland_wallbox_modus", "PV-Überschuss", { friendly_name: "Wallbox Lademodus", options: ["Aus", "Sofort", "PV-Überschuss", "Min + PV"] }),
    e("input_number.jotunland_wallbox_min_ampere", 6, { friendly_name: "Wallbox min. Strom", min: 6, max: 16, step: 1, unit_of_measurement: "A", mode: "slider" }),
    e("input_number.jotunland_wallbox_max_ampere", 16, { friendly_name: "Wallbox max. Strom", min: 6, max: 32, step: 1, unit_of_measurement: "A", mode: "slider" }),
    e("input_number.jotunland_wallbox_phasen", 3, { friendly_name: "Wallbox Phasen", min: 1, max: 3, step: 1, mode: "box" }),
    e("input_number.jotunland_komfort_temperatur", 21.5, { friendly_name: "Komforttemperatur", min: 16, max: 25, step: 0.5, unit_of_measurement: "°C", mode: "slider" }),
    e("input_number.jotunland_eco_temperatur", 18, { friendly_name: "Absenktemperatur", min: 12, max: 21, step: 0.5, unit_of_measurement: "°C", mode: "slider" }),
    e("input_number.jotunland_warmwasser_minimum", 45, { friendly_name: "Warmwasser Minimum", min: 35, max: 60, step: 1, unit_of_measurement: "°C", mode: "slider" }),
    e("input_datetime.jotunland_heizen_start", "06:00:00", { friendly_name: "Heizen ab", has_date: false, has_time: true }),
    e("input_datetime.jotunland_heizen_ende", "22:00:00", { friendly_name: "Absenken ab", has_date: false, has_time: true }),

    e("automation.jotunland_wallbox_pv_ueberschuss", "on", { id: "jotunland_wallbox_pv_ueberschuss", friendly_name: "Wallbox: PV-Überschussladen", last_triggered: now() }),
    e("automation.jotunland_heizzeiten", "on", { id: "jotunland_heizzeiten", friendly_name: "Heizung: Heizzeiten", last_triggered: now() }),
    e("automation.jotunland_abwesenheit", "on", { id: "jotunland_abwesenheit", friendly_name: "Heizung: Abwesenheit", last_triggered: null }),
    e("automation.jotunland_fenster_wohnzimmer", "on", { id: "jotunland_fenster_wohnzimmer", friendly_name: "Fenster offen → Wohnzimmer aus", last_triggered: null }),
    e("automation.jotunland_wallbox_pv_pause", "on", { id: "jotunland_wallbox_pv_pause", friendly_name: "Wallbox: Pause bei zu wenig Sonne", last_triggered: null }),
    e("automation.jotunland_pelletvorrat_niedrig", "on", { id: "jotunland_pelletvorrat_niedrig", friendly_name: "Pelletkessel: Vorrat niedrig", last_triggered: null }),
    e("automation.jotunland_pellet_stoerung", "on", { id: "jotunland_pellet_stoerung", friendly_name: "Pelletkessel: Störung melden", last_triggered: null }),
    e("automation.jotunland_warmwasser_nachheizen", "off", { id: "jotunland_warmwasser_nachheizen", friendly_name: "Warmwasser: Pellet-Nachheizung", last_triggered: null }),
    e("script.jotunland_alles_aus", "off", { friendly_name: "Alles aus (Verlassen)" }),
    e("script.jotunland_heizung_boost", "off", { friendly_name: "Heizung Boost 1 h" }),
    e("script.jotunland_auto_sofort_laden", "off", { friendly_name: "Auto sofort laden" }),
  ];
  return Object.fromEntries(list.map((x) => [x.entity_id, x]));
}

export interface DemoHome {
  call(domain: string, service: string, data?: Record<string, unknown>): Promise<void>;
  /** Teilmenge der WebSocket-API (Registries, Benutzerdaten) */
  ws<T>(msg: Record<string, unknown>): Promise<T>;
  stop(): void;
}

export function startDemo(onChange: (s: HassEntities) => void): DemoHome {
  const states = initialStates();
  const reg = initialRegistry();
  const push = () => onChange({ ...states });

  const set = (id: string, state?: string | number, attrs?: Record<string, unknown>) => {
    const old = states[id];
    if (!old) return;
    const t = now();
    states[id] = {
      ...old,
      state: state === undefined ? old.state : String(state),
      attributes: { ...old.attributes, ...attrs },
      last_updated: t,
      last_changed: state !== undefined && String(state) !== old.state ? t : old.last_changed,
    };
  };

  const num = (id: string) => Number(states[id]?.state ?? 0);

  // Physik light: Sonne schwankt, Wallbox folgt dem Überschuss, Netz ergibt sich daraus.
  const tick = () => {
    const prev = num("sensor.envoy_122301_current_power_production");
    const pv = Math.max(0, Math.min(9800, prev + (Math.random() - 0.5) * 500 + (5200 - prev) * 0.1));
    const house = 350 + Math.random() * 500 + (states["switch.kaffeemaschine"].state === "on" ? 1200 : 0);
    const charging = states["switch.wallbox_laden"].state === "on";
    const mode = states["input_select.jotunland_wallbox_modus"].state;
    let amps = num("number.wallbox_ladestrom_ampere");
    if (mode === "PV-Überschuss" || mode === "Min + PV") {
      amps = Math.max(6, Math.min(16, Math.floor((pv - house) / 690)));
      set("number.wallbox_ladestrom_ampere", amps);
    }
    const wb = charging && mode !== "Aus" ? amps * 690 : 0;
    const thor = Math.max(0, Math.min(3000, pv - house - wb));
    const water = Math.min(num("number.ac_thor_soll_temperatur"), num("sensor.ac_thor_temperatur") + thor / 20000);
    set("sensor.envoy_122301_current_power_production", Math.round(pv));
    set("sensor.envoy_122301_current_power_consumption", Math.round(house + wb + thor));
    set("sensor.envoy_122301_current_net_power_consumption", Math.round(house + wb + thor - pv));
    set("sensor.wallbox_leistung", Math.round(wb));
    set("sensor.wallbox_status", wb > 0 ? "Lädt" : "Bereit");
    set("sensor.ac_thor_leistung", Math.round(thor));
    set("sensor.ac_thor_temperatur", Math.round(water * 10) / 10);
    for (const id of Object.keys(states).filter((k) => k.startsWith("climate."))) {
      const c = states[id].attributes;
      const cur = Number(c.current_temperature);
      const target = states[id].state === "off" ? 5 : Number(c.temperature);
      const next = Math.round((cur + Math.sign(target - cur) * 0.1) * 10) / 10;
      set(id, undefined, { current_temperature: next, hvac_action: states[id].state === "off" ? "off" : next < target ? "heating" : "idle" });
    }
    push();
  };

  const timer = window.setInterval(tick, 3000);
  push();

  const targets = (data?: Record<string, unknown>): string[] => {
    const id = data?.entity_id;
    return Array.isArray(id) ? (id as string[]) : id ? [String(id)] : [];
  };

  return {
    stop: () => window.clearInterval(timer),
    async ws<T>(msg: Record<string, unknown>): Promise<T> {
      const { type, ...rest } = msg;
      switch (type) {
        case "config/area_registry/list":
          return demoAreas as T;
        case "config/device_registry/list":
          return reg.devices.map((d) => ({ ...d })) as T;
        case "config/entity_registry/list":
          return reg.entities.map((x) => ({ ...x })) as T;
        case "config/device_registry/update": {
          const d = reg.devices.find((x) => x.id === rest.device_id);
          if (!d) throw new Error("Gerät nicht gefunden");
          if ("name_by_user" in rest) d.name_by_user = rest.name_by_user as string;
          if ("area_id" in rest) d.area_id = rest.area_id as string;
          return d as T;
        }
        case "config/entity_registry/update": {
          const x = reg.entities.find((r) => r.entity_id === rest.entity_id);
          if (!x) throw new Error("Entität nicht gefunden");
          if ("area_id" in rest) x.area_id = rest.area_id as string;
          if ("name" in rest) {
            set(x.entity_id, undefined, { friendly_name: rest.name });
            push();
          }
          return x as T;
        }
        default:
          throw new Error(`Demo kennt ${String(type)} nicht`);
      }
    },
    async call(_domain, service, data) {
      for (const id of targets(data)) {
        const cur = states[id];
        if (!cur) continue;
        const d = id.split(".")[0];
        if (service === "toggle") set(id, cur.state === "on" ? "off" : "on");
        else if (service === "turn_on" && d === "script") {
          set(id, "on");
          window.setTimeout(() => {
            set(id, "off");
            push();
          }, 1500);
        } else if (service === "turn_on") set(id, "on", data?.brightness_pct ? { brightness: Math.round((Number(data.brightness_pct) / 100) * 255) } : undefined);
        else if (service === "turn_off") set(id, "off");
        else if (service === "trigger") set(id, undefined, { last_triggered: now() });
        else if (service === "set_temperature") set(id, undefined, { temperature: data?.temperature });
        else if (service === "set_hvac_mode") set(id, String(data?.hvac_mode));
        else if (service === "set_value") set(id, String(data?.value));
        else if (service === "select_option") set(id, String(data?.option));
        else if (service === "set_datetime") set(id, String(data?.time));
        else if (service === "open_cover") set(id, "open", { current_position: 100 });
        else if (service === "close_cover") set(id, "closed", { current_position: 0 });
        else if (service === "stop_cover") set(id, cur.state);
      }
      push();
    },
  };
}
