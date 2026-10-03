import { AlertTriangle, BatteryCharging, BatteryMedium, Car, Droplets, Flame, Sun } from "lucide-react";
import { useMemo } from "react";
import { useEntity, useHass } from "../ha/HassContext";
import { MYPV } from "../discovery";
import { fmtClock, startOfDay, useRuns } from "../history";
import { DayStrip, runSummary } from "./Timeline";
import { fmtNum, fmtPower, fmtState, fmtTemp, num, unavailable, watts } from "../format";
import { Badge, Bar, Card, Chips, Empty, Stat, Toggle } from "./ui";
import { HelperControl } from "./controls";
import { useEnergy } from "./EnergyFlow";

function Missing({ what }: { what: string }) {
  return <Empty>{what} noch nicht zugeordnet – unter <a href="#/einrichtung">Einrichtung</a> auswählen.</Empty>;
}

export function PvCard() {
  const n = useEnergy();
  const today = useEntity("energy.pv_today");
  const peak = 9800; // Anzeigeskala; bei Bedarf an die kWp der Anlage anpassen
  if (n.pv === undefined) return <Card title="Solar" icon={Sun} tone="sun"><Missing what="Die Enphase-Anlage ist" /></Card>;
  // Autarkie: Anteil des Verbrauchs, der nicht aus dem Netz kommt (PV und Batterie zählen beide)
  const selfUse = n.consumption
    ? n.grid !== undefined
      ? Math.max(0, Math.min(100, (1 - Math.max(n.grid, 0) / Math.max(n.consumption, 1)) * 100))
      : Math.min(100, (Math.min(n.pv, n.consumption) / Math.max(n.consumption, 1)) * 100)
    : undefined;
  return (
    <Card title="Solar" icon={Sun} tone="sun" action={<Badge tone={n.pv > 50 ? "ok" : "muted"}>{n.pv > 50 ? "produziert" : "ruht"}</Badge>}>
      <div className="stats">
        <Stat big label="Aktuell" value={fmtPower(n.pv)} />
        <Stat label="Heute" value={today ? fmtState(today) : "–"} />
        <Stat label="Autarkie" value={selfUse === undefined ? "–" : `${fmtNum(selfUse, 0)} %`} />
      </div>
      <Bar value={n.pv} max={peak} tone="sun" />
      {n.grid !== undefined && (
        <p className="hint">{n.grid < 0 ? `${fmtPower(-n.grid)} Überschuss werden eingespeist.` : `${fmtPower(n.grid)} kommen aus dem Netz.`}</p>
      )}
    </Card>
  );
}

export function BatteryCard() {
  const { entities, mapping } = useHass();
  const n = useEnergy();
  if (!mapping["energy.battery_power"] && !mapping["energy.battery_soc"]) return null;
  const b = n.battery;
  const zustand = b === undefined || Math.abs(b) <= 20 ? "ruht" : b > 0 ? "entlädt" : "lädt";
  const vorrang = entities["input_number.jotunland_batterie_vorrang"];
  return (
    <Card title="Batterie" icon={BatteryMedium} tone="battery" action={<Badge tone={zustand === "lädt" ? "ok" : zustand === "entlädt" ? "info" : "muted"}>{zustand}</Badge>}>
      <div className="stats">
        <Stat big label="Ladestand" value={n.batterySoc === undefined ? "–" : `${fmtNum(n.batterySoc, 0)} %`} />
        <Stat label={b !== undefined && b > 20 ? "Entladen" : "Laden"} value={fmtPower(b === undefined ? undefined : Math.abs(b))} />
      </div>
      <Bar value={n.batterySoc} max={100} tone="battery" />
      {vorrang && (
        <>
          <HelperControl entity={vorrang} label="Vorrang vor dem Auto bis" />
          <p className="hint">Bis zu diesem Ladestand bekommt die Batterie den Überschuss zuerst, darüber lädt das Auto mit. Warmwasser kommt nach dem Auto.</p>
        </>
      )}
    </Card>
  );
}

export function WallboxCard() {
  const { callService } = useHass();
  const status = useEntity("wallbox.status");
  const power = useEntity("wallbox.power");
  const session = useEntity("wallbox.session_energy");
  const sw = useEntity("wallbox.charging_switch");
  const current = useEntity("wallbox.current");
  const mode = useEntity("wallbox.mode");
  if (!status && !power && !sw) return <Card title="Wallbox" icon={Car} tone="bolt"><Missing what="Die Wallbox ist" /></Card>;
  const w = watts(power) ?? 0;
  const charging = w > 100;
  return (
    <Card
      title="Wallbox"
      icon={Car}
      tone="bolt"
      action={sw?.entity_id.startsWith("switch.") && <Toggle on={sw.state === "on"} disabled={unavailable(sw)} label="Laden" onChange={(v) => callService("switch", v ? "turn_on" : "turn_off", { entity_id: sw.entity_id })} />}
    >
      <div className="stats">
        <Stat big label="Ladeleistung" value={fmtPower(w)} sub={charging ? <Badge tone="ok"><BatteryCharging size={12} /> lädt</Badge> : status ? fmtState(status) : undefined} />
        <Stat label="Geladen" value={session ? fmtState(session) : "–"} />
        <Stat label="Strom" value={current ? fmtState(current) : "–"} />
      </div>
      {mode && <HelperControl entity={mode} label="Lademodus" />}
      {sw?.entity_id.startsWith("select.") && (
        <div className="helper wide">
          <span className="helper-label">Ladefreigabe</span>
          <Chips value={sw.state} options={((sw.attributes.options as string[]) ?? []).map((o) => ({ value: o, label: o }))} onChange={(o) => callService("select", "select_option", { entity_id: sw.entity_id, option: o })} />
        </div>
      )}
      {current && mode?.state !== "PV-Überschuss" && mode?.state !== "Min + PV" && <HelperControl entity={current} label="Ladestrom" />}
      {current && (mode?.state === "PV-Überschuss" || mode?.state === "Min + PV") && <p className="hint">Der Ladestrom wird automatisch an den PV-Überschuss angepasst.</p>}
    </Card>
  );
}

const CONTROL_ORDER = ["input_select", "select", "input_boolean", "switch", "input_number", "number", "input_button", "button", "script"];

/** Alle Stellschrauben des AC THOR – auch die der eigenen Regelung (Modus, Handleistung …) */
function useAcThorControls() {
  const { infos } = useHass();
  return useMemo(
    () =>
      infos
        .filter((i) => CONTROL_ORDER.includes(i.domain) && MYPV.test(i.own) && i.entity.state !== "unavailable")
        .sort((a, b) => CONTROL_ORDER.indexOf(a.domain) - CONTROL_ORDER.indexOf(b.domain) || a.name.localeCompare(b.name, "de")),
    [infos],
  );
}

export function AcThorCard() {
  const { infos } = useHass();
  const power = useEntity("acthor.power");
  const temp = useEntity("acthor.temperature");
  const target = useEntity("acthor.target");
  const controls = useAcThorControls();
  const today = useMemo(() => startOfDay(Date.now()), []);
  const { runs } = useRuns([power?.entity_id], today);
  if (!power && !temp) return <Card title="Warmwasser · AC THOR" icon={Droplets} tone="water"><Missing what="Der AC THOR ist" /></Card>;
  const t = num(temp);
  const tt = target?.attributes.unit_of_measurement === "°C" ? num(target) : undefined;
  const w = watts(power) ?? 0;
  const todayRuns = power ? runs[power.entity_id] ?? [] : [];

  // Warum heizt er nicht? Speicher voll sperrt auch den Handbetrieb.
  // Temperaturgrenze der eigenen Regelung, z. B. input_number.ac_thor_max_temp_messwert
  const limit = controls.find((c) => (c.domain === "input_number" || c.domain === "number") && c.unit === "°C" && /max|grenze|limit/.test(c.own));
  const limitVal = limit ? num(limit.entity) : undefined;
  const full = infos.find((i) => i.domain === "binary_sensor" && MYPV.test(i.own) && /voll|full|sperr|block/.test(i.own) && i.entity.state === "on");
  // Handbetrieb: Auswahl "Modus = Hand" oder ein Schalter "…Handbetrieb…" = an
  const hand =
    controls.find((c) => c.domain.endsWith("select") && /modus|mode|betrieb/.test(c.own) && /hand|manu/i.test(c.entity.state)) ??
    controls.find((c) => (c.domain === "input_boolean" || c.domain === "switch") && /hand|manu/.test(c.own) && c.entity.state === "on");
  const handSince = hand ? Date.parse(hand.entity.last_changed) : undefined;
  const handButIdle = handSince !== undefined && !full && w < 50 && Date.now() - handSince > 90_000;

  return (
    <Card title="Warmwasser · AC THOR" icon={Droplets} tone="water" action={w > 50 ? <Badge tone="warn"><Flame size={12} /> heizt</Badge> : <Badge tone="muted">aus</Badge>}>
      <div className="stats">
        <Stat big label="Speicher" value={fmtTemp(t)} sub={tt !== undefined ? `Soll ${fmtTemp(tt)}` : undefined} />
        <Stat label="Heizstab" value={fmtPower(w)} />
      </div>
      <Bar value={t} max={tt ?? 70} tone="water" />
      {full && (
        <p className="hint bad">
          „{full.name}“ ist an – deine Regelung heizt dann nicht, auch nicht im Handbetrieb.
          {t !== undefined && limitVal !== undefined && (
            <>
              {" "}Messwert {fmtTemp(t)}, Grenze {fmtTemp(limitVal)}.
              {t < limitVal - 5
                ? " Der Messwert liegt deutlich unter der Grenze – die Sperre müsste eigentlich aus sein. Bitte die Regelung prüfen (Verlauf)."
                : " Die Sperre geht erst wieder aus, wenn der Messwert um die Hysterese unter die Grenze fällt. Zum Freigeben die Grenze unten erhöhen."}
            </>
          )}
        </p>
      )}
      {handButIdle && (
        <p className="hint bad">
          Handbetrieb ist seit {fmtClock(handSince!)} an, aber der Heizstab nimmt keine Leistung auf. Mögliche Gründe: Temperaturgrenze, Modbus-Verbindung
          oder Watchdog der Regelung – die Entscheidungen stehen im <a href="#/verlauf">Verlauf</a>.
        </p>
      )}
      {controls.length > 0 && (
        <div className="helpers">
          {controls.map((c) => (
            <HelperControl key={c.id} entity={c.entity} label={c.name.replace(/^(my-?pv\s*)?ac[ -]?thor\s*/i, "") || c.name} />
          ))}
        </div>
      )}
      {power && (
        <a className="today-runs" href="#/verlauf">
          <DayStrip runs={todayRuns} day={today} tone="water" />
          <span>Heute: {runSummary(todayRuns)} →</span>
        </a>
      )}
    </Card>
  );
}

function Tank({ top, bottom }: { top?: number; bottom?: number }) {
  const color = (v?: number) => (v === undefined ? "var(--muted)" : `hsl(${Math.max(0, Math.min(220, 220 - (v - 20) * 4))} 75% 55%)`);
  return (
    <div className="tank" aria-label="Pufferspeicher">
      <div className="tank-fill" style={{ background: `linear-gradient(${color(top)}, ${color(bottom)})` }} />
      <span className="tank-top">{fmtNum(top, 0)}°</span>
      <span className="tank-bottom">{fmtNum(bottom, 0)}°</span>
    </div>
  );
}

export function PelletCard() {
  const state = useEntity("pellet.state");
  const boiler = useEntity("pellet.boiler_temp");
  const top = useEntity("pellet.buffer_top");
  const bottom = useEntity("pellet.buffer_bottom");
  const outside = useEntity("pellet.outside_temp");
  const stock = useEntity("pellet.pellet_stock");
  const error = useEntity("pellet.error");
  if (!state && !boiler) return <Card title="Pelletkessel · Fröling" icon={Flame} tone="fire"><Missing what="Der Fröling-Kessel ist" /></Card>;
  const fault = error && (error.state === "on" || (!["off", "0", "ok", "keine", "unavailable", "unknown", ""].includes(error.state.toLowerCase()) && !error.entity_id.startsWith("binary_sensor.")));
  const stockVal = num(stock);
  return (
    <Card title="Pelletkessel · Fröling" icon={Flame} tone="fire" action={fault ? <Badge tone="bad"><AlertTriangle size={12} /> Störung</Badge> : state ? <Badge tone="muted">{fmtState(state)}</Badge> : undefined}>
      <div className="pellet">
        <div className="stats">
          <Stat big label="Kessel" value={fmtTemp(num(boiler))} />
          <Stat label="Außen" value={fmtTemp(num(outside))} />
          {stock && <Stat label="Vorrat" value={fmtState(stock)} />}
        </div>
        {(top || bottom) && <Tank top={num(top)} bottom={num(bottom)} />}
      </div>
      {stock && stock.attributes.unit_of_measurement === "%" && <Bar value={stockVal} tone={stockVal !== undefined && stockVal < 20 ? "bad" : "fire"} />}
      {fault && <p className="hint bad">{error!.entity_id.startsWith("binary_sensor.") ? "Der Kessel meldet eine Störung." : fmtState(error)}</p>}
    </Card>
  );
}
