import { Car, Droplets, Home, Sun, UtilityPole } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { fmtPower, watts } from "../format";

export interface EnergyNumbers {
  pv?: number;
  grid?: number;
  consumption?: number;
  wallbox?: number;
  acthor?: number;
  house?: number;
}

/** Leitet fehlende Werte aus den vorhandenen ab (Energiebilanz: PV + Netz = Verbrauch). */
export function useEnergy(): EnergyNumbers {
  const { entities, mapping } = useHass();
  const w = (slot: string) => watts(mapping[slot] ? entities[mapping[slot]!] : undefined);
  const pv = w("energy.pv_power");
  let grid = w("energy.grid");
  let consumption = w("energy.consumption");
  if (grid === undefined && pv !== undefined && consumption !== undefined) grid = consumption - pv;
  if (consumption === undefined && pv !== undefined && grid !== undefined) consumption = pv + grid;
  const wallbox = w("wallbox.power");
  const acthor = w("acthor.power");
  const house = consumption === undefined ? undefined : Math.max(0, consumption - (wallbox ?? 0) - (acthor ?? 0));
  return { pv, grid, consumption, wallbox, acthor, house };
}

const NODES: Record<string, { x: number; y: number; icon: LucideIcon; label: string; tone: string }> = {
  pv: { x: 160, y: 34, icon: Sun, label: "Solar", tone: "sun" },
  grid: { x: 40, y: 160, icon: UtilityPole, label: "Netz", tone: "grid" },
  acthor: { x: 280, y: 160, icon: Droplets, label: "Warmwasser", tone: "water" },
  wallbox: { x: 160, y: 290, icon: Car, label: "Wallbox", tone: "bolt" },
};
const HUB = { x: 160, y: 160 };
const H = 340;

export function EnergyFlow() {
  const n = useEnergy();
  const flows: { key: keyof typeof NODES; value?: number; toHub: boolean; sub?: string }[] = [
    { key: "pv", value: n.pv, toHub: true },
    { key: "grid", value: n.grid === undefined ? undefined : Math.abs(n.grid), toHub: (n.grid ?? 0) > 0, sub: n.grid === undefined ? undefined : n.grid > 0 ? "Bezug" : "Einspeisung" },
    { key: "acthor", value: n.acthor, toHub: false },
    { key: "wallbox", value: n.wallbox, toHub: false },
  ];

  return (
    <div className="flow">
      <svg viewBox={`0 0 320 ${H}`} role="img" aria-label="Energiefluss">
        {flows.map((f) => {
          const node = NODES[f.key];
          const active = (f.value ?? 0) > 20;
          const [x1, y1, x2, y2] = f.toHub ? [node.x, node.y, HUB.x, HUB.y] : [HUB.x, HUB.y, node.x, node.y];
          return <line key={f.key} x1={x1} y1={y1} x2={x2} y2={y2} className={`flow-line tone-${node.tone} ${active ? "active" : ""}`} />;
        })}
      </svg>
      {flows.map((f) => {
        const node = NODES[f.key];
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
