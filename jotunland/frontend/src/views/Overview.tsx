import { ChevronRight, Home, Plane, Sparkles, Thermometer, Zap } from "lucide-react";
import { INTERNAL_SCRIPT, useSetupState } from "../setup";
import { useHass } from "../ha/HassContext";
import { Card, Empty, Toggle } from "../components/ui";
import { EnergyFlow } from "../components/EnergyFlow";
import { AcThorCard, PelletCard, WallboxCard } from "../components/systems";
import { fmtNum, fmtTarget, name } from "../format";

function greeting() {
  const h = new Date().getHours();
  return h < 11 ? "Guten Morgen" : h < 18 ? "Hallo" : "Guten Abend";
}

export function Overview() {
  const { entities, rooms, callService, config } = useHass();
  const away = entities["input_boolean.jotunland_abwesend"];
  const setup = useSetupState();
  const scripts = Object.values(entities).filter((e) => e.entity_id.startsWith("script.jotunland_") && !INTERNAL_SCRIPT.test(e.entity_id));

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

      {setup.open > 0 && (
        <a className="setup-banner" href="#/einrichtung">
          <Sparkles size={18} />
          <span>
            <strong>Einrichtung abschließen</strong> – noch {setup.open} {setup.open === 1 ? "Schritt" : "Schritte"}, jeweils mit einem Klick erledigt.
          </span>
          <ChevronRight size={18} />
        </a>
      )}

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
                    <small>{c.state === "off" ? "aus" : `→ ${fmtTarget(c.attributes)}`}</small>
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

      </div>
    </div>
  );
}
