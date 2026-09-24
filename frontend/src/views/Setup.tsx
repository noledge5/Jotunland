import { useMemo, useState } from "react";
import { Check, Copy, Download, FileCode, LogOut, Search, Sparkles, Wand2 } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { logout } from "../ha/connection";
import { Badge, Card, Chips, Empty } from "../components/ui";
import { candidatesFor, KIND_LABEL, SLOTS, suggestDevices, type DeviceSuggestion } from "../discovery";
import { fmtState, name, norm } from "../format";
import { renderPackage } from "../haPackage";

const SOURCE_LABEL = { manual: "von dir gewählt", config: "config.json", auto: "automatisch erkannt", none: "fehlt" } as const;
const SOURCE_TONE = { manual: "ok", config: "info", auto: "info", none: "bad" } as const;

function MappingTab() {
  const { infos, entities, mapping, mappingSource, overrides, setOverride, config } = useHass();
  const groups = useMemo(() => {
    const g = new Map<string, string[]>();
    for (const [key, rule] of Object.entries(SLOTS)) g.set(rule.group, [...(g.get(rule.group) ?? []), key]);
    return [...g.entries()];
  }, []);

  const exportConfig = () => {
    const out: Record<string, unknown> = { ...config };
    for (const key of Object.keys(SLOTS)) {
      const [group, field] = key.split(".");
      out[group] = { ...(out[group] as object), [field]: mapping[key] ?? null };
    }
    download("config.json", JSON.stringify(out, null, 2), "application/json");
  };

  const found = Object.values(mappingSource).filter((s) => s !== "none").length;

  return (
    <>
      <p className="lead">
        <Sparkles size={16} />
        <span>{found} von {Object.keys(SLOTS).length} Funktionen sind zugeordnet. Die Erkennung bewertet Hersteller und Integration, Einheit und Namen. Stimmt ein Vorschlag nicht, wähle einfach eine andere Entität. Die Auswahl wird in deinem Home-Assistant-Benutzerkonto gespeichert.</span>
      </p>
      <div className="grid">
        {groups.map(([group, keys]) => (
          <Card key={group} title={group}>
            <ul className="mapping">
              {keys.map((key) => {
                const cands = candidatesFor(key, infos);
                const current = mapping[key];
                const src = mappingSource[key];
                const inList = !current || cands.some((c) => c.id === current);
                return (
                  <li key={key}>
                    <div className="mapping-head">
                      <strong>{SLOTS[key].label}</strong>
                      <Badge tone={SOURCE_TONE[src]}>{SOURCE_LABEL[src]}</Badge>
                    </div>
                    <select
                      className="input"
                      value={current ?? ""}
                      onChange={(ev) => setOverride(key, ev.target.value || null)}
                    >
                      <option value="">– nicht vorhanden –</option>
                      {!inList && current && <option value={current}>{current}</option>}
                      {cands.slice(0, 12).map((c) => (
                        <option key={c.id} value={c.id}>
                          {name(entities[c.id])} · {fmtState(entities[c.id])} ({c.id})
                        </option>
                      ))}
                    </select>
                    <div className="mapping-foot">
                      {current && entities[current] ? <span className="muted">aktuell: {fmtState(entities[current])}</span> : <span className="muted">{cands.length ? `${cands.length} Kandidaten` : "keine passende Entität gefunden"}</span>}
                      {overrides[key] && <button type="button" className="link" onClick={() => setOverride(key, null)}>automatisch</button>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </div>
      <button type="button" className="btn" onClick={exportConfig}><Download size={14} /> Als config.json exportieren</button>
    </>
  );
}

function DevicesTab() {
  const { infos, devices, areas, ws, refreshRegistry, registryAvailable } = useHass();
  const [onlyTodo, setOnlyTodo] = useState("todo");
  const [busy, setBusy] = useState<string>();
  const [err, setErr] = useState<string>();
  const list = useMemo(() => suggestDevices(infos, devices, areas), [infos, devices, areas]);
  const todo = list.filter((s) => s.suggestedName || s.suggestedArea);
  const shown = onlyTodo === "todo" ? todo : list;

  if (!registryAvailable) return <Empty>Die Geräteliste braucht einen Home-Assistant-Benutzer mit Administratorrechten.</Empty>;

  const apply = async (s: DeviceSuggestion, what: "name" | "area" | "both") => {
    const msg: Record<string, unknown> = { type: "config/device_registry/update", device_id: s.device.id };
    if ((what === "name" || what === "both") && s.suggestedName) msg.name_by_user = s.suggestedName;
    if ((what === "area" || what === "both") && s.suggestedArea) msg.area_id = s.suggestedArea.area_id;
    await ws(msg);
  };

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setErr(undefined);
    try {
      await fn();
      await refreshRegistry();
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <>
      <div className="toolbar">
        <p className="lead">
          <Wand2 size={16} />
          <span>{list.length} Geräte erkannt, {todo.length} mit Vorschlag. Technische Namen wie „0x00158d…“ oder „TS0601“ bekommen einen Namen nach dem Muster „Typ Raum“. Fehlt der Raum, wird er aus Namen und IDs erraten.</span>
        </p>
        <Chips value={onlyTodo} onChange={setOnlyTodo} options={[{ value: "todo", label: "Mit Vorschlag" }, { value: "all", label: "Alle Geräte" }]} />
      </div>
      {todo.length > 1 && (
        <button
          type="button"
          className="btn primary"
          disabled={!!busy}
          onClick={() => confirm(`${todo.length} Vorschläge in Home Assistant übernehmen?`) && run("all", async () => { for (const s of todo) await apply(s, "both"); })}
        >
          <Check size={14} /> Alle Vorschläge übernehmen
        </button>
      )}
      {err && <p className="hint bad">{err}</p>}
      {shown.length === 0 ? (
        <Empty>Alles sauber benannt 🎉</Empty>
      ) : (
        <ul className="rows devices">
          {shown.map((s) => (
            <li key={s.device.id}>
              <div className="row-text">
                <span className="kind">{KIND_LABEL[s.kind]}</span>
                <strong>
                  {s.currentName} {s.technical && <Badge tone="warn">technischer Name</Badge>}
                </strong>
                <small>
                  {[s.device.manufacturer, s.device.model].filter(Boolean).join(" · ")} · {s.entities.length} Entitäten · {s.areaName ?? "kein Raum"}
                </small>
                {(s.suggestedName || s.suggestedArea) && (
                  <div className="suggest">
                    {s.suggestedName && <span>→ <b>{s.suggestedName}</b></span>}
                    {s.suggestedArea && <span>Raum: <b>{s.suggestedArea.name}</b></span>}
                  </div>
                )}
              </div>
              {(s.suggestedName || s.suggestedArea) && (
                <button type="button" className="btn small" disabled={!!busy} onClick={() => run(s.device.id, () => apply(s, "both"))}>
                  {busy === s.device.id ? "…" : "Übernehmen"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function EntitiesTab() {
  const { entities } = useHass();
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const query = norm(q);
    return Object.values(entities)
      .filter((e) => !query || norm(`${e.entity_id} ${name(e)} ${e.attributes.device_class ?? ""}`).includes(query))
      .sort((a, b) => a.entity_id.localeCompare(b.entity_id))
      .slice(0, 300);
  }, [entities, q]);
  return (
    <>
      <label className="search">
        <Search size={16} />
        <input placeholder="entity_id, Name oder Geräteklasse …" value={q} onChange={(ev) => setQ(ev.target.value)} />
      </label>
      <ul className="rows compact">
        {list.map((e) => (
          <li key={e.entity_id} onClick={() => navigator.clipboard?.writeText(e.entity_id)} title="Klicken zum Kopieren">
            <div className="row-text">
              <strong>{name(e)}</strong>
              <small className="mono">{e.entity_id}</small>
            </div>
            <span className="muted">{fmtState(e)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function download(filename: string, content: string, type: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function PackageTab() {
  const { mapping } = useHass();
  const { yaml, missing } = useMemo(() => renderPackage(mapping), [mapping]);
  const [copied, setCopied] = useState(false);
  return (
    <>
      <p className="lead">
        <FileCode size={16} />
        <span>
          Automationen, Skripte und Helfer für Home Assistant, schon mit deinen Geräten ausgefüllt. Speichere die Datei als <code>/config/packages/jotunland.yaml</code>, prüfe unter Entwicklerwerkzeuge → YAML die Konfiguration und starte Home Assistant neu.
        </span>
      </p>
      {missing.length > 0 && (
        <p className="hint bad">
          Noch nicht zugeordnet: {missing.map((m) => SLOTS[m]?.label ?? m).join(", ")}. Diese Stellen bleiben als „anpassen_…“ in der Datei stehen.
        </p>
      )}
      <div className="btn-row">
        <button type="button" className="btn primary" onClick={() => download("jotunland.yaml", yaml, "text/yaml")}><Download size={14} /> jotunland.yaml herunterladen</button>
        <button type="button" className="btn" onClick={() => navigator.clipboard?.writeText(yaml).then(() => setCopied(true))}><Copy size={14} /> {copied ? "Kopiert" : "Kopieren"}</button>
      </div>
      <pre className="code">{yaml}</pre>
    </>
  );
}

function ConnectionTab() {
  const { settings, applySettings, status, entities, isDemo } = useHass();
  return (
    <Card title="Verbindung">
      <ul className="rows">
        <li><div className="row-text"><strong>Modus</strong><small>{isDemo ? "Demo (simuliert)" : settings.mode === "token" ? "Zugriffstoken" : "Home-Assistant-Anmeldung"}</small></div></li>
        <li><div className="row-text"><strong>Server</strong><small>{settings.url || window.location.origin}</small></div></li>
        <li><div className="row-text"><strong>Status</strong><small>{status} · {Object.keys(entities).length} Entitäten</small></div></li>
      </ul>
      <div className="btn-row">
        {isDemo ? (
          <button type="button" className="btn" onClick={() => applySettings(null)}>Demo beenden</button>
        ) : (
          <button type="button" className="btn" onClick={() => { logout(); applySettings(null); }}><LogOut size={14} /> Abmelden</button>
        )}
      </div>
    </Card>
  );
}

export function Setup() {
  const [tab, setTab] = useState("mapping");
  return (
    <div className="view">
      <header className="view-head">
        <h1>Einrichtung</h1>
      </header>
      <Chips
        value={tab}
        onChange={setTab}
        options={[
          { value: "mapping", label: "Zuordnung" },
          { value: "devices", label: "Geräte benennen" },
          { value: "package", label: "HA-Paket" },
          { value: "entities", label: "Entitäten" },
          { value: "connection", label: "Verbindung" },
        ]}
      />
      <div className="tab-body">
        {tab === "mapping" && <MappingTab />}
        {tab === "devices" && <DevicesTab />}
        {tab === "package" && <PackageTab />}
        {tab === "entities" && <EntitiesTab />}
        {tab === "connection" && <ConnectionTab />}
      </div>
    </div>
  );
}
