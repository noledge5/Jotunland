import { SlidersHorizontal, Thermometer } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Card, Empty } from "../components/ui";
import { HelperControl, Thermostat } from "../components/controls";
import { AcThorCard, PelletCard } from "../components/systems";

const HEATING_HELPERS = [
  "input_number.jotunland_komfort_temperatur",
  "input_number.jotunland_eco_temperatur",
  "input_datetime.jotunland_heizen_start",
  "input_datetime.jotunland_heizen_ende",
  "input_boolean.jotunland_sommerbetrieb",
  "input_number.jotunland_warmwasser_minimum",
];

export function Heating() {
  const { entities, rooms } = useHass();
  const helpers = HEATING_HELPERS.map((id) => entities[id]).filter(Boolean);
  return (
    <div className="view">
      <header className="view-head">
        <h1>Heizung</h1>
      </header>
      <h2 className="section-title"><Thermometer size={16} /> Räume</h2>
      {rooms.length === 0 ? (
        <Empty>Keine Thermostate (climate.*) gefunden.</Empty>
      ) : (
        <div className="grid thermo-grid">
          {rooms.map((r) =>
            entities[r.climate] ? (
              <Thermostat key={r.climate} entity={entities[r.climate]} title={r.name} windowSensor={r.window ? entities[r.window] : undefined} humidity={r.humidity ? entities[r.humidity] : undefined} />
            ) : null,
          )}
        </div>
      )}
      <h2 className="section-title">Wärmeerzeuger</h2>
      <div className="grid">
        <PelletCard />
        <AcThorCard />
        {helpers.length > 0 && (
          <Card title="Heizprogramm" icon={SlidersHorizontal}>
            <div className="helpers">
              {helpers.map((h) => (
                <HelperControl key={h.entity_id} entity={h} />
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
