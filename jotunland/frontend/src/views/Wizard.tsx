import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Loader2 } from "lucide-react";
import { useHass } from "../ha/HassContext";
import { Badge } from "../components/ui";
import { SLOTS } from "../discovery";
import { HELPER_MARKER, useSetupActions, useSetupState } from "../setup";

/** Wie das jeweilige Gerät in Home Assistant kommt */
const INTEGRATION_HINTS: Record<string, ReactNode> = {
  Solar: (
    <>
      Integration „Enphase Envoy“ einrichten –{" "}
      <a className="link" href="https://my.home-assistant.io/redirect/config_flow_start/?domain=enphase_envoy" target="_blank" rel="noreferrer">direkt starten</a>{" "}
      (IP des Envoy und Enlighten-Zugang bereithalten).
    </>
  ),
  Wallbox: "go-e: in der go-e App unter Internet → Erweiterte Einstellungen „HTTP API v2“ aktivieren, dann in HACS „go-eCharger (APIv2)“ installieren und einrichten.",
  "AC THOR": "my-PV: in HACS nach „my-PV“ suchen – oder mit Claude Code auf deinem PC direkt per IP anbinden (siehe README).",
  Pelletkessel: "Fröling: in HACS nach „Fröling“ suchen (Fröling Connect) – oder mit Claude Code auf deinem PC anbinden.",
};

function Step({ n, done, title, children, actions }: { n: number; done: boolean; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <li className={`step ${done ? "done" : ""}`}>
      <span className="step-mark">{done ? <Check size={16} /> : n}</span>
      <div className="step-body">
        <strong>{title}</strong>
        {children && <div className="step-text">{children}</div>}
        {actions && <div className="btn-row">{actions}</div>}
      </div>
    </li>
  );
}

/** Schritt für Schritt zum fertigen Zuhause – jeder offene Punkt mit Ein-Klick-Aktion. */
export function Wizard({ goTo }: { goTo: (tab: string) => void }) {
  const { status, entities, devices, addon, isDemo, callService, registryAvailable, refreshAddon } = useHass();
  const st = useSetupState();
  const act = useSetupActions();
  const [busy, setBusy] = useState<string>();
  const [result, setResult] = useState<{ ok: boolean; text: string; steps?: string[] }>();
  const [restarting, setRestarting] = useState(false);
  const sawDisconnect = useRef(false);

  // Nach der Installation startet HA neu: warten, bis die Verbindung wieder steht
  useEffect(() => {
    if (!restarting) return;
    if (status === "reconnecting") sawDisconnect.current = true;
    if (status === "connected" && sawDisconnect.current && entities[HELPER_MARKER]) {
      setRestarting(false);
      sawDisconnect.current = false;
      refreshAddon();
      setResult({ ok: true, text: "Home Assistant ist neu gestartet – die Automationen laufen. Die Startwerte werden automatisch gesetzt." });
    }
  }, [restarting, status, entities, refreshAddon]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setResult(undefined);
    try {
      await fn();
    } catch (err) {
      const data = (err as { data?: { steps?: string[] } }).data;
      setResult({ ok: false, text: err instanceof Error ? err.message : String(err), steps: data?.steps });
    } finally {
      setBusy(undefined);
    }
  };

  const install = () =>
    run("install", async () => {
      if (!confirm("Automationen jetzt installieren? Home Assistant wird dafür einmal neu gestartet (ca. 1 Minute). Vorher wird eine Sicherung angelegt.")) return;
      const res = await act.installPackage(st.pkg.yaml);
      setResult({ ok: true, text: "Installiert.", steps: res.steps });
      if (res.restarting) {
        sawDisconnect.current = false;
        setRestarting(true);
      }
    });

  const mode = entities[HELPER_MARKER];
  const found = st.groups.filter((g) => g.found).length;
  let n = 0;

  return (
    <>
      <p className="lead">
        <span>
          Offene Punkte lassen sich direkt hier erledigen. Alles, was Jotunland in Home Assistant ändert, lässt sich dort auch wieder rückgängig machen.
        </span>
      </p>
      <ol className="steps">
        <Step n={++n} done={status === "connected"} title="Mit Home Assistant verbunden">
          {Object.keys(entities).length} Entitäten, {Object.keys(devices).length} Geräte
          {addon ? " · als Add-on, automatisch angemeldet" : isDemo ? " · Demo-Modus" : ""}
        </Step>

        <Step
          n={++n}
          done={found === st.groups.length}
          title={`Geräte erkannt (${found} von ${st.groups.length})`}
          actions={<button type="button" className="btn small" onClick={() => goTo("mapping")}>Zuordnung ansehen</button>}
        >
          <div className="chips">
            {st.groups.map((g) => (
              <Badge key={g.group} tone={g.found ? "ok" : "bad"}>{g.found ? "✓" : "✗"} {g.group}</Badge>
            ))}
          </div>
          {st.groups
            .filter((g) => !g.found)
            .map((g) => (
              <p key={g.group} className="hint">
                <b>{g.group}:</b> {INTEGRATION_HINTS[g.group]}
              </p>
            ))}
          {found < st.groups.length && (
            <p className="hint">
              Ist die Integration schon eingerichtet, die Entität unter Zuordnung auswählen. Übersicht:{" "}
              <a className="link" href="https://my.home-assistant.io/redirect/integrations/" target="_blank" rel="noreferrer">Geräte &amp; Dienste</a>
            </p>
          )}
        </Step>

        <Step
          n={++n}
          done={st.suggestions.length === 0}
          title={st.suggestions.length ? `${st.suggestions.length} Geräte verständlich benennen` : "Gerätenamen sind aufgeräumt"}
          actions={
            st.suggestions.length > 0 && (
              <>
                <button
                  type="button"
                  className="btn primary small"
                  disabled={!!busy || !registryAvailable}
                  onClick={() => run("names", () => act.applySuggestions(st.suggestions))}
                >
                  {busy === "names" ? <Loader2 size={14} className="spin" /> : <Check size={14} />} Alle übernehmen
                </button>
                <button type="button" className="btn small" onClick={() => goTo("devices")}>Einzeln ansehen</button>
              </>
            )
          }
        >
          {st.suggestions.length > 0 && (
            <span className="muted">
              z. B. {st.suggestions.slice(0, 3).map((s) => `„${s.currentName}“ → ${s.suggestedName ? `„${s.suggestedName}“` : `Raum ${s.suggestedArea?.name}`}`).join(", ")}
            </span>
          )}
        </Step>

        <Step
          n={++n}
          done={st.packageCurrent}
          title={st.packageCurrent ? "Automationen installiert" : addon?.package.installed ? "Automationen aktualisieren" : "Automationen installieren"}
          actions={
            !st.packageCurrent &&
            (addon && addon.setup.automatic ? (
              <button type="button" className="btn primary small" disabled={!!busy || restarting} onClick={install}>
                {busy === "install" || restarting ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                {restarting ? " Home Assistant startet neu …" : addon.package.installed ? " Aktualisieren" : " Installieren"}
              </button>
            ) : (
              <button type="button" className="btn small" onClick={() => goTo("package")}>Paket ansehen / herunterladen</button>
            ))
          }
        >
          PV-Überschussladen, Heizzeiten, Abwesenheit, Sommerbetrieb, Warmwasser-Nachheizung und Kesselmeldungen
          {st.windowRooms > 0 && `, dazu „Fenster offen → Heizung aus“ für ${st.windowRooms} ${st.windowRooms === 1 ? "Raum" : "Räume"}`}.
          {st.pkg.missing.length > 0 && !st.packageCurrent && (
            <p className="hint">Ohne Zuordnung (diese Teile bleiben inaktiv): {st.pkg.missing.map((m) => SLOTS[m]?.label ?? m).join(", ")}</p>
          )}
          {addon && !addon.setup.automatic && <p className="hint bad">{addon.setup.note}</p>}
          {addon && addon.load_errors?.length > 0 && (
            <p className="hint bad">Home Assistant meldet beim Laden: {addon.load_errors.join(" · ")}</p>
          )}
          {!addon && !isDemo && <p className="hint">Tipp: Als Home-Assistant-Add-on installiert Jotunland das Paket selbst (siehe README).</p>}
          {isDemo && <p className="hint">Im Demo-Modus wird nichts installiert.</p>}
        </Step>

        {st.helpersInstalled && (
          <Step
            n={++n}
            done={st.helpersNeedingDefaults.length === 0}
            title="Startwerte setzen"
            actions={
              st.helpersNeedingDefaults.length > 0 && (
                <button type="button" className="btn small" disabled={!!busy} onClick={() => run("defaults", act.applyDefaults)}>
                  Startwerte setzen
                </button>
              )
            }
          >
            Wallbox 16 A / 3 Phasen, 21 °C komfort, 18 °C abgesenkt, Heizen 6–22 Uhr, Warmwasser mind. 45 °C. Anpassen kannst du alles unter Automationen.
          </Step>
        )}

        {mode && (
          <Step
            n={++n}
            done={mode.state !== "Aus"}
            title={mode.state === "Aus" ? "PV-Überschussladen einschalten" : `Wallbox-Modus: ${mode.state}`}
            actions={
              mode.state === "Aus" && (
                <button type="button" className="btn small" onClick={() => callService("input_select", "select_option", { entity_id: mode.entity_id, option: "PV-Überschuss" })}>
                  Einschalten
                </button>
              )
            }
          >
            Das Auto lädt dann nur mit Sonnenstrom, der sonst ins Netz ginge.
          </Step>
        )}

        <Step n={++n} done={!!addon} title="Aufs Handy und von unterwegs">
          {addon
            ? "Jotunland steht in der Seitenleiste von Home Assistant, also auch in der Home-Assistant-App auf dem Handy. Unterwegs funktioniert es über Home Assistant Cloud (Nabu Casa) oder dein VPN."
            : "Installiere Jotunland als Add-on, dann steht es automatisch in der Seitenleiste und in der Home-Assistant-App."}
        </Step>
      </ol>

      {result && (
        <div className={`result ${result.ok ? "ok" : "bad"}`}>
          <strong>{result.text}</strong>
          {result.steps && (
            <ul>
              {result.steps.map((s) => <li key={s}>{s}</li>)}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
