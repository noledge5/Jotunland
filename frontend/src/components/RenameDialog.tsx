import { useState } from "react";
import { X } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { name } from "../format";

/** Entität umbenennen und einem Raum zuordnen – schreibt direkt in die HA-Registry. */
export function RenameDialog({ entityId, suggestion, onClose }: { entityId: string; suggestion?: string; onClose: () => void }) {
  const { entities, areas, meta, ws, refreshRegistry, registryAvailable } = useHass();
  const e = entities[entityId];
  const [value, setValue] = useState(name(e));
  const [area, setArea] = useState(meta[entityId]?.area_id ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();

  const save = async () => {
    setBusy(true);
    setErr(undefined);
    try {
      await ws({ type: "config/entity_registry/update", entity_id: entityId, name: value.trim() || null, ...(area !== (meta[entityId]?.area_id ?? "") ? { area_id: area || null } : {}) });
      await refreshRegistry();
      onClose();
    } catch (x) {
      setErr(x instanceof Error ? x.message : "Speichern fehlgeschlagen (Admin-Rechte nötig, Entität braucht eine unique_id).");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
        <header>
          <h2>Umbenennen</h2>
          <button type="button" className="icon-btn" aria-label="Schließen" onClick={onClose}><X size={18} /></button>
        </header>
        <p className="mono muted">{entityId}</p>
        <label className="field">
          <span>Name</span>
          <input className="input" value={value} autoFocus onChange={(ev) => setValue(ev.target.value)} onKeyDown={(ev) => ev.key === "Enter" && save()} />
        </label>
        {suggestion && suggestion !== value && (
          <button type="button" className="chip" onClick={() => setValue(suggestion)}>Vorschlag: {suggestion}</button>
        )}
        {registryAvailable && (
          <label className="field">
            <span>Raum</span>
            <select className="input" value={area} onChange={(ev) => setArea(ev.target.value)}>
              <option value="">– wie Gerät –</option>
              {areas.map((a) => <option key={a.area_id} value={a.area_id}>{a.name}</option>)}
            </select>
          </label>
        )}
        {err && <p className="hint bad">{err}</p>}
        <footer>
          <button type="button" className="btn ghost" onClick={onClose}>Abbrechen</button>
          <button type="button" className="btn primary" disabled={busy} onClick={save}>Speichern</button>
        </footer>
      </div>
    </div>
  );
}
