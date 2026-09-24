import { useEffect, useRef, useState } from "react";
import type { HassEntity } from "home-assistant-js-websocket";
import {
  AppWindow, Battery, Blinds, Droplet, Flame, Gauge, Lightbulb, Minus, Play, Plug, Plus, Power, Snowflake, Thermometer, ToggleRight, Wind,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { fmtNum, fmtState, fmtTarget, fmtTemp, name, relTime, unavailable } from "../format";
import { Badge, Chips, Slider, Toggle } from "./ui";

const HVAC_LABEL: Record<string, string> = { heat: "Heizen", auto: "Auto", off: "Aus", cool: "Kühlen", heat_cool: "Auto", dry: "Trocknen", fan_only: "Lüfter" };

/** Thermostat mit ±-Tasten. Änderungen werden gesammelt und nach kurzer Pause gesendet. */
export function Thermostat({ entity, title, windowSensor, humidity }: { entity: HassEntity; title?: string; windowSensor?: HassEntity; humidity?: HassEntity }) {
  const { callService } = useHass();
  const a = entity.attributes;
  const step = Number(a.target_temp_step ?? 0.5);
  const min = Number(a.min_temp ?? 5);
  const max = Number(a.max_temp ?? 30);
  const serverTarget = a.temperature === undefined || a.temperature === null ? undefined : Number(a.temperature);
  const [target, setTarget] = useState(serverTarget);
  const timer = useRef<number>(undefined);

  useEffect(() => {
    if (!timer.current) setTarget(serverTarget);
  }, [serverTarget]);

  const change = (delta: number) => {
    const next = Math.min(max, Math.max(min, Math.round(((target ?? 20) + delta) / step) * step));
    setTarget(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = undefined;
      callService("climate", "set_temperature", { entity_id: entity.entity_id, temperature: next });
    }, 700);
  };

  const off = entity.state === "off";
  const heating = a.hvac_action === "heating";
  const windowOpen = windowSensor?.state === "on";
  const modes = ((a.hvac_modes as string[] | undefined) ?? []).filter((m) => HVAC_LABEL[m]);
  const battery = a.battery ?? a.battery_level;

  return (
    <div className={`thermo ${heating ? "heating" : ""} ${off ? "off" : ""}`}>
      <div className="thermo-head">
        <h3>{title ?? name(entity)}</h3>
        <div className="thermo-badges">
          {windowOpen && <Badge tone="info"><AppWindow size={12} /> Fenster offen</Badge>}
          {heating && <Badge tone="warn"><Flame size={12} /> heizt</Badge>}
          {battery !== undefined && Number(battery) < 25 && <Badge tone="bad"><Battery size={12} /> {String(battery)} %</Badge>}
          {unavailable(entity) && <Badge tone="bad">offline</Badge>}
        </div>
      </div>
      <div className="thermo-body">
        <div className="thermo-current">
          <span className="thermo-value">{fmtNum(a.current_temperature == null ? undefined : Number(a.current_temperature), 1)}</span>
          <span className="thermo-unit">°C</span>
          {humidity && <div className="thermo-hum"><Droplet size={12} /> {fmtState(humidity)}</div>}
        </div>
        <div className="thermo-target">
          <button type="button" className="round" aria-label="Kälter" disabled={off || unavailable(entity)} onClick={() => change(-step)}>
            <Minus size={18} />
          </button>
          <div className="thermo-set">
            <small>Soll</small>
            <strong>{off ? "Aus" : target === undefined ? fmtTarget(a) : fmtTemp(target)}</strong>
          </div>
          <button type="button" className="round" aria-label="Wärmer" disabled={off || unavailable(entity)} onClick={() => change(step)}>
            <Plus size={18} />
          </button>
        </div>
      </div>
      {modes.length > 1 && (
        <Chips
          value={entity.state}
          options={modes.map((m) => ({ value: m, label: HVAC_LABEL[m] }))}
          onChange={(m) => callService("climate", "set_hvac_mode", { entity_id: entity.entity_id, hvac_mode: m })}
        />
      )}
    </div>
  );
}

/** Bedienelement für Helfer (input_*) und number-Entitäten – die "Stellschrauben" der Automationen. */
export function HelperControl({ entity, label }: { entity: HassEntity; label?: string }) {
  const { callService } = useHass();
  const id = entity.entity_id;
  const domain = id.split(".")[0];
  const a = entity.attributes;
  const title = label ?? name(entity);

  let control: React.ReactNode = <span className="muted">{fmtState(entity)}</span>;
  if (domain === "input_boolean" || domain === "switch") {
    control = <Toggle on={entity.state === "on"} label={title} onChange={(v) => callService(domain, v ? "turn_on" : "turn_off", { entity_id: id })} />;
  } else if (domain === "input_number" || domain === "number") {
    const min = Number(a.min ?? 0);
    const max = Number(a.max ?? 100);
    const step = Number(a.step ?? 1);
    const unit = a.unit_of_measurement ? ` ${a.unit_of_measurement}` : "";
    control = (
      <Slider
        value={Number(entity.state)}
        min={min}
        max={max}
        step={step}
        format={(v) => `${fmtNum(v, step < 1 ? 1 : 0)}${unit}`}
        onCommit={(v) => callService(domain, "set_value", { entity_id: id, value: v })}
      />
    );
  } else if (domain === "input_select" || domain === "select") {
    const options = (a.options as string[]) ?? [];
    control = <Chips value={entity.state} options={options.map((o) => ({ value: o, label: o }))} onChange={(o) => callService(domain, "select_option", { entity_id: id, option: o })} />;
  } else if (domain === "input_datetime" && a.has_time && !a.has_date) {
    control = (
      <input
        type="time"
        className="input time"
        value={entity.state.slice(0, 5)}
        onChange={(ev) => ev.target.value && callService("input_datetime", "set_datetime", { entity_id: id, time: `${ev.target.value}:00` })}
      />
    );
  } else if (domain === "script" || domain === "input_button" || domain === "button") {
    control = (
      <button type="button" className="btn" onClick={() => callService(domain, domain === "script" ? "turn_on" : "press", { entity_id: id })}>
        <Play size={14} /> Start
      </button>
    );
  }

  const wide = domain === "input_select" || domain === "select" || domain === "input_number" || domain === "number";
  return (
    <div className={`helper ${wide ? "wide" : ""}`}>
      <span className="helper-label">{title}</span>
      {control}
    </div>
  );
}

function iconFor(e: HassEntity): LucideIcon {
  const d = e.entity_id.split(".")[0];
  const dc = e.attributes.device_class;
  if (d === "light") return Lightbulb;
  if (d === "switch") return dc === "outlet" || /steckdose|plug/i.test(e.entity_id) ? Plug : Power;
  if (d === "cover") return Blinds;
  if (d === "climate") return Thermometer;
  if (d === "fan") return Wind;
  if (dc === "temperature") return Thermometer;
  if (dc === "humidity" || dc === "moisture") return Droplet;
  if (dc === "window" || dc === "door" || dc === "opening") return AppWindow;
  if (dc === "power" || dc === "energy") return Gauge;
  if (dc === "battery") return Battery;
  if (d === "input_boolean") return ToggleRight;
  return Snowflake;
}

/** Kachel für die Geräteübersicht: bedienbar, wo sinnvoll, sonst Anzeige. */
export function EntityTile({ entity, onRename }: { entity: HassEntity; onRename?: () => void }) {
  const { callService } = useHass();
  const id = entity.entity_id;
  const d = id.split(".")[0];
  const Icon = iconFor(entity);
  const on = ["on", "open", "heat", "auto"].includes(entity.state);
  const toggleable = ["light", "switch", "input_boolean", "fan"].includes(d);
  const dimmable = d === "light" && ((entity.attributes.supported_color_modes as string[] | undefined) ?? []).some((m) => m !== "onoff");

  return (
    <div className={`tile ${on ? "on" : ""} ${unavailable(entity) ? "unavail" : ""}`} data-domain={d}>
      <div className="tile-top">
        <span className="tile-icon"><Icon size={18} /></span>
        <div className="tile-text">
          <button type="button" className="tile-name" onClick={onRename} title={id}>{name(entity)}</button>
          <span className="tile-state">{fmtState(entity)}{d === "light" && on && entity.attributes.brightness ? ` · ${Math.round((Number(entity.attributes.brightness) / 255) * 100)} %` : ""}</span>
        </div>
        {toggleable && <Toggle on={entity.state === "on"} disabled={unavailable(entity)} label={name(entity)} onChange={(v) => callService(d, v ? "turn_on" : "turn_off", { entity_id: id })} />}
      </div>
      {dimmable && entity.state === "on" && (
        <Slider value={Math.round((Number(entity.attributes.brightness ?? 255) / 255) * 100)} min={1} max={100} step={1} format={(v) => `${v} %`} onCommit={(v) => callService("light", "turn_on", { entity_id: id, brightness_pct: v })} />
      )}
      {d === "cover" && (
        <div className="btn-row">
          <button type="button" className="btn small" onClick={() => callService("cover", "open_cover", { entity_id: id })}>Auf</button>
          <button type="button" className="btn small" onClick={() => callService("cover", "stop_cover", { entity_id: id })}>Stopp</button>
          <button type="button" className="btn small" onClick={() => callService("cover", "close_cover", { entity_id: id })}>Zu</button>
        </div>
      )}
      {(d === "sensor" || d === "binary_sensor") && <span className="tile-foot">{relTime(entity.last_changed)}</span>}
    </div>
  );
}
