import { useState } from "react";
import { Mountain } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Chips } from "../components/ui";

/** Erster Start außerhalb von Home Assistant: Server-Adresse und Anmeldeart wählen. */
export function Connect() {
  const { applySettings, error, status, settings } = useHass();
  const [mode, setMode] = useState<"auto" | "token">(settings.mode === "token" ? "token" : "auto");
  const [url, setUrl] = useState(settings.url ?? "http://homeassistant.local:8123");
  const [token, setToken] = useState(settings.token ?? "");

  return (
    <div className="connect">
      <div className="connect-card">
        <div className="brand big"><Mountain size={28} /> Jotunland</div>
        <p className="muted">Mit Home Assistant verbinden</p>
        {status === "error" && <p className="hint bad">{error}</p>}
        <label className="field">
          <span>Home-Assistant-Adresse</span>
          <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://homeassistant.local:8123" />
        </label>
        <Chips value={mode} onChange={(v) => setMode(v as "auto" | "token")} options={[{ value: "auto", label: "HA-Anmeldung" }, { value: "token", label: "Zugriffstoken" }]} />
        {mode === "token" && (
          <label className="field">
            <span>Langlebiges Zugriffstoken</span>
            <textarea className="input" rows={3} value={token} onChange={(e) => setToken(e.target.value)} placeholder="Profil → Sicherheit → Token erstellen" />
          </label>
        )}
        <button type="button" className="btn primary" disabled={!url || (mode === "token" && !token)} onClick={() => applySettings({ mode, url: url.trim(), token: mode === "token" ? token.trim() : undefined })}>
          Verbinden
        </button>
        <button type="button" className="btn ghost" onClick={() => applySettings({ mode: "demo" })}>
          Erst mal die Demo ansehen
        </button>
      </div>
    </div>
  );
}
