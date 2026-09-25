import { BatteryMedium, Car, Droplets, Home, Sun, UtilityPole } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { fmtNum, fmtPower, num, watts } from "../format";

export interface EnergyNumbers {
  pv?: number;
  /** + Bezug / − Einspeisung */
  grid?: number;
  /** + Entladen / − Laden */
  battery?: number;
  batterySoc?: number;
  /** alles, was im Haus verbraucht wird (inkl. Wallbox und Warmwasser, ohne Batterieladung) */
  consumption?: number;
  wallbox?: number;
  acthor?: number;
  house?: number;
}

/**
 * Energiebilanz: PV + Netz + Batterie = Verbrauch.
 * Sind PV und Netz bekannt, wird der Verbrauch daraus berechnet – der "Verbrauch" mancher
 * Zähler (z. B. Enphase mit Netz-CT) ist selbst nur PV + Netz und zählt das Laden der
 * Batterie als Verbrauch.
 */
export function useEnergy(): EnergyNumbers {
  const { entities, mapping } = useHass();
  const entity = (slot: string) => (mapping[slot] ? entities[mapping[slot]!] : undefined);
  const w = (slot: string) => watts(entity(slot));
  const pv = w("energy.pv_power");
  const battery = w("energy.battery_power");
  const batterySoc = num(entity("energy.battery_soc"));
  let grid = w("energy.grid");
  let consumption = w("energy.consumption");
  if (pv !== undefined && grid !== undefined) consumption = pv + grid + (battery ?? 0);
  else if (grid === undefined && pv !== undefined && consumption !== undefined) grid = consumption - pv - (battery ?? 0);
  const wallbox = w("wallbox.power");
  const acthor = w("acthor.power");
  const house = consumption === undefined ? undefined : Math.max(0, consumption - (wallbox ?? 0) - (acthor ?? 0));
  return { pv, grid, battery, batterySoc, consumption, wallbox, acthor, house };
}

const NODES: Record<string, { x: number; y: number; icon: LucideIcon; label: string; tone: string }> = {
  pv: { x: 160, y: 34, icon: Sun, label: "Solar", tone: "sun" },
  grid: { x: 40, y: 160, icon: UtilityPole, label: "Netz", tone: "grid" },
  acthor: { x: 280, y: 160, icon: Droplets, label: "Warmwasser", tone: "water" },
  battery: { x: 64, y: 312, icon: BatteryMedium, label: "Batterie", tone: "battery" },
  wallbox: { x: 256, y: 312, icon: Car, label: "Wallbox", tone: "bolt" },
};
const HUB = { x: 160, y: 160 };
// Höhe passend zu aspect-ratio von .flow in styles.css
const H = 392;

export function EnergyFlow() {
  const { mapping } = useHass();
  const n = useEnergy();
  const soc = n.batterySoc === undefined ? undefined : `${fmtNum(n.batterySoc, 0)} %`;
  const flows: { key: keyof typeof NODES; value?: number; toHub: boolean; sub?: string }[] = [
    { key: "pv", value: n.pv, toHub: true },
    { key: "grid", value: n.grid === undefined ? undefined : Math.abs(n.grid), toHub: (n.grid ?? 0) > 0, sub: n.grid === undefined ? undefined : n.grid > 0 ? "Bezug" : "Einspeisung" },
    { key: "acthor", value: n.acthor, toHub: false },
    { key: "wallbox", value: n.wallbox, toHub: false },
  ];
  // Die Batterie nur zeigen, wenn es eine gibt – sonst steht die Wallbox mittig unten
  const withBattery = !!(mapping["energy.battery_power"] || mapping["energy.battery_soc"]);
  const nodeOf = (key: keyof typeof NODES) => (key === "wallbox" && !withBattery ? { ...NODES.wallbox, x: HUB.x } : NODES[key]);
  if (withBattery) {
    const b = n.battery;
    const richtung = b === undefined || Math.abs(b) <= 20 ? undefined : b > 0 ? "entlädt" : "lädt";
    flows.push({
      key: "battery",
      value: b === undefined ? undefined : Math.abs(b),
      toHub: (b ?? 0) > 0,
      sub: [soc, richtung].filter(Boolean).join(" · ") || undefined,
    });
  }

  return (
    <div className="flow">
      <svg viewBox={`0 0 320 ${H}`} role="img" aria-label="Energiefluss">
        {flows.map((f) => {
          const node = nodeOf(f.key);
          const active = (f.value ?? 0) > 20;
          const [x1, y1, x2, y2] = f.toHub ? [node.x, node.y, HUB.x, HUB.y] : [HUB.x, HUB.y, node.x, node.y];
          return <line key={f.key} x1={x1} y1={y1} x2={x2} y2={y2} className={`flow-line tone-${node.tone} ${active ? "active" : ""}`} />;
        })}
      </svg>
      {flows.map((f) => {
        const node = nodeOf(f.key);
        const Icon = node.icon;
        return (
          <div key={f.key} className={`flow-node tone-${node.tone} ${f.value === undefined ? "missing" : ""}`} style={{ left: `${(node.x / 320) * 100}%`, top: `${(node.y / H) * 100}%` }}>
            <span className="flow-bubble">
              <Icon size={20} />
            </span>
            <strong>{fmtPower(f.value)}</strong>
            <small>{f.sub ?? node.label}</small>
          </div>
        );
      })}
      <div className="flow-node hub" style={{ left: "50%", top: `${(HUB.y / H) * 100}%` }}>
        <span className="flow-bubble">
          <Home size={22} />
        </span>
        <strong>{fmtPower(n.house)}</strong>
        <small>Haus</small>
      </div>
    </div>
  );
}
