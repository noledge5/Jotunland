import { Home, Plane, Thermometer, Zap } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Card, Empty, Toggle } from "../components/ui";
import { EnergyFlow } from "../components/EnergyFlow";
import { AcThorCard, PelletCard, WallboxCard } from "../components/systems";
import { fmtNum, name } from "../format";

function greeting() {
  const h = new Date().getHours();
  return h < 11 ? "Guten Morgen" : h < 18 ? "Hallo" : "Guten Abend";
}

export function Overview() {
  const { entities, rooms, callService, config } = useHass();
  const away = entities["input_boolean.jotunland_abwesend"];
  const scripts = Object.values(entities).filter((e) => e.entity_id.startsWith("script.jotunland_"));

  return (
    <div className="view">
      <header className="view-head">
        <div>
          <p className="eyebrow">{new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}</p>
          <h1>{greeting()} in {config.title}</h1>
        </div>
        {away && (
          <label className="away">
            <Plane size={16} /> Abwesend
            <Toggle on={away.state === "on"} label="Abwesend" onChange={(v) => callService("input_boolean", v ? "turn_on" : "turn_off", { entity_id: away.entity_id })} />
          </label>
        )}
      </header>

      <div className="grid">
        <Card title="Energie jetzt" icon={Zap} className="span-2">
          <EnergyFlow />
        </Card>

        <Card title="Räume" icon={Thermometer} action={<a className="link" href="#/heizung">Alle</a>}>
          {rooms.length === 0 ? (
            <Empty>Keine Thermostate gefunden.</Empty>
          ) : (
            <ul className="room-list">
              {rooms.map((r) => {
                const c = entities[r.climate];
                const w = r.window ? entities[r.window] : undefined;
                if (!c) return null;
                return (
                  <li key={r.climate} className={c.attributes.hvac_action === "heating" ? "heating" : ""}>
                    <span>{r.name}{w?.state === "on" && <em> · Fenster offen</em>}</span>
                    <strong>{fmtNum(c.attributes.current_temperature == null ? undefined : Number(c.attributes.current_temperature), 1)}°</strong>
                    <small>{c.state === "off" ? "aus" : `→ ${fmtNum(Number(c.attributes.temperature), 1)}°`}</small>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <WallboxCard />
        <AcThorCard />
        <PelletCard />

        {scripts.length > 0 && (
          <Card title="Schnellaktionen" icon={Home}>
            <div className="quick">
              {scripts.map((s) => (
                <button key={s.entity_id} type="button" className={`quick-btn ${s.state === "on" ? "running" : ""}`} onClick={() => callService("script", "turn_on", { entity_id: s.entity_id })}>
                  {name(s)}
                </button>
              ))}
            </div>
          </Card>
        )}

        {entities["input_select.jotunland_wallbox_modus"] === undefined && entities["input_boolean.jotunland_abwesend"] === undefined && (
          <Card title="Automationen einrichten" className="span-2">
            <Empty>
              Die Jotunland-Helfer (Abwesend, Lademodus, Heizzeiten …) fehlen noch in Home Assistant. Kopiere <code>homeassistant/packages/jotunland.yaml</code> nach <code>/config/packages/</code> – siehe README.
            </Empty>
          </Card>
        )}
      </div>
    </div>
  );
}
