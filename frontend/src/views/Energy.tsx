import { SlidersHorizontal, Zap } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Card } from "../components/ui";
import { EnergyFlow } from "../components/EnergyFlow";
import { HelperControl } from "../components/controls";
import { AcThorCard, PvCard, WallboxCard } from "../components/systems";

const ENERGY_HELPERS = ["input_number.jotunland_wallbox_min_ampere", "input_number.jotunland_wallbox_max_ampere", "input_number.jotunland_wallbox_phasen"];

export function Energy() {
  const { entities } = useHass();
  const helpers = ENERGY_HELPERS.map((id) => entities[id]).filter(Boolean);
  return (
    <div className="view">
      <header className="view-head">
        <h1>Energie</h1>
      </header>
      <div className="grid">
        <Card title="Energiefluss" icon={Zap} className="span-2">
          <EnergyFlow />
        </Card>
        <PvCard />
        <WallboxCard />
        <AcThorCard />
        {helpers.length > 0 && (
          <Card title="PV-Überschussladen" icon={SlidersHorizontal}>
            <div className="helpers">
              {helpers.map((h) => (
                <HelperControl key={h.entity_id} entity={h} />
              ))}
            </div>
            <p className="hint">Geladen wird, sobald der Überschuss für den Mindeststrom reicht. Fällt er 5 Minuten darunter, pausiert die Wallbox.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
