import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Chips, Empty } from "../components/ui";
import { EntityTile } from "../components/controls";
import { RenameDialog } from "../components/RenameDialog";
import { name, norm } from "../format";

const CONTROLS = ["light", "switch", "cover", "fan", "lock", "climate"];
const SENSORS = ["sensor", "binary_sensor"];

export function Devices() {
  const { entities, areas, meta } = useHass();
  const [filter, setFilter] = useState("controls");
  const [q, setQ] = useState("");
  const [rename, setRename] = useState<string>();

  const groups = useMemo(() => {
    const domains = filter === "controls" ? CONTROLS : filter === "sensors" ? SENSORS : [...CONTROLS, ...SENSORS];
    const query = norm(q);
    const list = Object.values(entities).filter((e) => {
      const d = e.entity_id.split(".")[0];
      if (!domains.includes(d) || meta[e.entity_id]?.hidden) return false;
      return !query || norm(`${e.entity_id} ${name(e)}`).includes(query);
    });
    const byArea = new Map<string, typeof list>();
    for (const e of list) {
      const a = meta[e.entity_id]?.area_id ?? "";
      byArea.set(a, [...(byArea.get(a) ?? []), e]);
    }
    const ordered = [...areas.map((a) => ({ id: a.area_id, title: a.name })), { id: "", title: "Ohne Raum" }];
    return ordered
      .map((g) => ({ ...g, items: (byArea.get(g.id) ?? []).sort((x, y) => name(x).localeCompare(name(y), "de")) }))
      .filter((g) => g.items.length);
  }, [entities, areas, meta, filter, q]);

  return (
    <div className="view">
      <header className="view-head">
        <h1>Geräte</h1>
      </header>
      <div className="toolbar">
        <label className="search">
          <Search size={16} />
          <input placeholder="Suchen …" value={q} onChange={(ev) => setQ(ev.target.value)} />
        </label>
        <Chips value={filter} onChange={setFilter} options={[{ value: "controls", label: "Bedienbar" }, { value: "sensors", label: "Sensoren" }, { value: "all", label: "Alle" }]} />
      </div>
      {groups.length === 0 && <Empty>Nichts gefunden.</Empty>}
      {groups.map((g) => (
        <section key={g.id} className="area-group">
          <h2 className="section-title">{g.title} <span className="count">{g.items.length}</span></h2>
          <div className="tiles">
            {g.items.map((e) => (
              <EntityTile key={e.entity_id} entity={e} onRename={() => setRename(e.entity_id)} />
            ))}
          </div>
        </section>
      ))}
      <p className="hint">Tipp: Auf einen Namen tippen, um ihn umzubenennen oder einem Raum zuzuordnen.</p>
      {rename && <RenameDialog entityId={rename} onClose={() => setRename(undefined)} />}
    </div>
  );
}
