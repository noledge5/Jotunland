import { useState } from "react";
import { Play, ScrollText, SlidersHorizontal, Workflow } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Card, Chips, Empty, Toggle } from "../components/ui";
import { HelperControl } from "../components/controls";
import { name, relTime } from "../format";

const HELPER_DOMAINS = ["input_boolean", "input_number", "input_select", "input_datetime"];

export function Automations() {
  const { entities, callService } = useHass();
  const [scope, setScope] = useState("jotunland");
  const all = Object.values(entities);
  const mine = (id: string) => scope === "all" || id.split(".")[1].startsWith("jotunland");
  const automations = all.filter((e) => e.entity_id.startsWith("automation.") && mine(e.entity_id)).sort((a, b) => name(a).localeCompare(name(b), "de"));
  const scripts = all.filter((e) => e.entity_id.startsWith("script.") && mine(e.entity_id)).sort((a, b) => name(a).localeCompare(name(b), "de"));
  const helpers = all.filter((e) => HELPER_DOMAINS.includes(e.entity_id.split(".")[0]) && mine(e.entity_id));

  return (
    <div className="view">
      <header className="view-head">
        <h1>Automationen</h1>
        <Chips value={scope} onChange={setScope} options={[{ value: "jotunland", label: "Jotunland" }, { value: "all", label: "Alle" }]} />
      </header>
      <div className="grid">
        <Card title="Automationen" icon={Workflow} className="span-2">
          {automations.length === 0 ? (
            <Empty>Keine Automationen gefunden.</Empty>
          ) : (
            <ul className="rows">
              {automations.map((a) => (
                <li key={a.entity_id}>
                  <div className="row-text">
                    <strong>{name(a)}</strong>
                    <small>zuletzt ausgelöst: {relTime(a.attributes.last_triggered as string | null)}</small>
                  </div>
                  <button type="button" className="icon-btn" title="Jetzt ausführen" aria-label="Jetzt ausführen" onClick={() => callService("automation", "trigger", { entity_id: a.entity_id })}>
                    <Play size={16} />
                  </button>
                  <Toggle on={a.state === "on"} label="Aktiv" onChange={(v) => callService("automation", v ? "turn_on" : "turn_off", { entity_id: a.entity_id })} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Stellschrauben" icon={SlidersHorizontal}>
          {helpers.length === 0 ? <Empty>Keine Helfer gefunden.</Empty> : <div className="helpers">{helpers.map((h) => <HelperControl key={h.entity_id} entity={h} />)}</div>}
        </Card>
        <Card title="Skripte" icon={ScrollText}>
          {scripts.length === 0 ? <Empty>Keine Skripte gefunden.</Empty> : <div className="helpers">{scripts.map((s) => <HelperControl key={s.entity_id} entity={s} />)}</div>}
        </Card>
      </div>
    </div>
  );
}
